"""Pure Application orchestration for one non-executable V3.1 research cycle.

The service binds independently validated Domain artifacts into one vertical
information -> data -> graph -> cloud -> scenario -> action-evaluation chain.
It deliberately seals the complete evaluation before accepting any selection
input.  It performs no IO, collection, model invocation, order construction,
or execution.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from ..domain.information_model import (
    AdmittedInformationEvent,
    InformationModelError,
    admit_information_event,
    build_information_event_revision_registry,
    information_event_to_canonical_dict,
)
from ..domain.agent_research_contract import (
    AgentResearchContractError,
    verify_v31_agent_proposal,
    verify_v31_inputs_receipt,
)
from ..domain.data_model import (
    DataModelError,
    DatumEpistemicType,
    PointInTimeDatum,
    QualityLevel,
    build_point_in_time_datum_revision_registry,
    point_in_time_datum_from_document,
    point_in_time_dataset_rows_from_document,
    verify_point_in_time_dataset,
)
from ..domain.association_estimation import (
    AssociationEstimationError,
    verify_pearson_association_receipt,
)
from ..domain.dynamic_research import (
    DynamicResearchError,
    TERMINAL_EXPECTATION_STATUSES,
    TERMINAL_HYPOTHESIS_STATES,
    build_market_information_snapshot,
    build_sentiment_state,
    migrate_legacy_sentiment_state_to_v31,
    verify_sentiment_state,
    verify_sentiment_state_change,
    reduce_expectation_ledger,
    reduce_hypothesis_registry,
)
from ..domain.market_knowledge_graph import (
    NODE_STAGE_ORDER,
    apply_graph_delta,
    verify_market_knowledge_graph,
)
from ..domain.probability_cloud import (
    ProbabilityCloud,
    ProbabilityCloudError,
    verify_probability_cloud_repartition,
    verify_probability_cloud_update,
)
from ..domain.behavior_planning import (
    ActionType,
    BehaviorPlanningError,
    PortfolioDecisionContext,
    seal_action_selection,
    verify_complete_action_evaluation,
)
from ..domain.scenario_path import (
    ImplicationEffect,
    PathFactSnapshot,
    PredicateQuality,
    PredicateTruth,
    ScenarioPathError,
    ScenarioPathSet,
    evaluate_path_conditions,
)


class V31ResearchCycleError(ValueError):
    """A V3.1 cross-layer cycle binding failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PRESELECTION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "inputs_receipt_digest",
        "agent_proposal_digest",
        "information_event_digests",
        "information_revision_registry_digest",
        "association_estimation_receipt_digests",
        "pit_dataset_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "prior_graph_digest",
        "graph_delta_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "probability_cloud_transition",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "path_evaluation",
        "action_evaluation_digest",
        "candidate_path_admissibility_digest",
        "candidate_path_admissibility",
        "selectable_candidate_ids",
        "artifact_bindings_digest",
        "binding_order",
        "graph_chain_policy",
        "selection_fields_admitted",
        "external_execution_authority",
        "executable",
        "preselection_digest",
    }
)
_ACCEPTED_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "selected_at",
        "symbol",
        "inputs_receipt_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_evaluation_digest",
        "action_selection_digest",
        "agent_proposal_digest",
        "selected_candidate_id",
        "selected_candidate_evaluation_digest",
        "status",
        "selection_boundary",
        "external_execution_authority",
        "executable",
        "accepted_state_digest",
    }
)
_COMPLETION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "selected_at",
        "completed_at",
        "inputs_receipt_digest",
        "accepted_state_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_selection_digest",
        "selected_candidate_id",
        "completion_status",
        "external_execution_authority",
        "executable",
        "completion_receipt_digest",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "selected_candidate_id",
        "ranked_alternative_ids",
        "why_not_selected",
        "selection_rationale",
        "action_selection_digest",
        "selected_candidate_evaluation_digest",
    }
)
_REQUIRED_GRAPH_TYPES = frozenset(
    {
        "INFORMATION_EVENT",
        "MARKET_FACT",
        "DERIVED_MEASURE",
        "LATENT_STATE",
        "EXPECTATION",
        "SCENARIO_PATH",
        "ACTION_CANDIDATE",
    }
)
_BINDING_ORDER = (
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
)

_RELATIONS_BY_ADJACENT_STAGE = {
    (1, 2): frozenset({"DESCRIBES", "EMITS", "TRANSMITS_TO"}),
    (2, 3): frozenset({"DERIVED_FROM"}),
    (3, 4): frozenset(
        {"CONDITIONED_BY", "ASSOCIATED_WITH", "LEADS", "SUPPORTS"}
    ),
    (4, 5): frozenset(
        {"SUPPORTS", "OPPOSES", "EXPLAINS", "ALTERNATIVE_TO", "EVALUATES"}
    ),
    (5, 6): frozenset({"PRODUCES", "INSTANTIATES", "SUPPORTS"}),
    (6, 7): frozenset({"INSTANTIATES", "TRIGGERS", "SUPPORTS"}),
    (7, 8): frozenset({"SUPPORTS", "OPPOSES", "TRIGGERS", "EVALUATES"}),
}

_ADVANCING_RELATIONS = frozenset(
    {
        "DESCRIBES",
        "EMITS",
        "TRANSMITS_TO",
        "DERIVED_FROM",
        "CONDITIONED_BY",
        "ASSOCIATED_WITH",
        "LEADS",
        "SUPPORTS",
        "EXPLAINS",
        "PRODUCES",
        "INSTANTIATES",
        "TRIGGERS",
        "EVALUATES",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31ResearchCycleError(code)
    return value.strip()


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ResearchCycleError(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31ResearchCycleError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ResearchCycleError(code) from exc
    if result.tzinfo is None:
        raise V31ResearchCycleError(code)
    return result.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_timestamp(value: Any, code: str) -> datetime:
    parsed = _timestamp(value, code)
    if value != _timestamp_text(parsed):
        raise V31ResearchCycleError(code)
    return parsed


def _document_refs(
    value: Any, code: str, *, allow_empty: bool = True
) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ) or len(value) != len(set(value)):
        raise V31ResearchCycleError(code)
    return value


def _contains_selection_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(set(value) & _SELECTION_FIELDS) or any(
            _contains_selection_field(item) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_selection_field(item) for item in value)
    return False


def _verify_self(document: Mapping[str, Any], field: str, code: str) -> str:
    try:
        return verify_self_digest(document, field)
    except ValueError as exc:
        raise V31ResearchCycleError(code) from exc


def _verify_canonical_document_digest(
    document: Mapping[str, Any], field: str, code: str
) -> str:
    supplied = _digest(document.get(field), code)
    payload = dict(document)
    payload.pop(field, None)
    if canonical_digest(payload) != supplied:
        raise V31ResearchCycleError(code)
    return supplied


def _merge_exact_bindings(
    *catalogs: Mapping[str, str], code: str
) -> dict[str, str]:
    merged: dict[str, str] = {}
    for catalog in catalogs:
        for ref, digest in catalog.items():
            if (
                not isinstance(ref, str)
                or not ref
                or _HEX_64.fullmatch(str(digest)) is None
            ):
                raise V31ResearchCycleError(code)
            previous = merged.get(ref)
            if previous is not None and previous != digest:
                raise V31ResearchCycleError(code)
            merged[ref] = str(digest)
    return merged


def _admit_information_chain(
    admissions: Sequence[AdmittedInformationEvent],
    *,
    decision_at: datetime,
    previous_information_revision_registry: Mapping[str, Any] | None = None,
) -> tuple[
    list[str],
    dict[str, str],
    set[str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    if not isinstance(admissions, (list, tuple)) or not admissions:
        raise V31ResearchCycleError("V31_INFORMATION_ADMISSIONS_REQUIRED")
    grouped: dict[str, list[AdmittedInformationEvent]] = defaultdict(list)
    for admission in admissions:
        if not isinstance(admission, AdmittedInformationEvent):
            raise V31ResearchCycleError("V31_INFORMATION_ADMISSION_INVALID")
        grouped[admission.event.event_id].append(admission)
    digests: list[str] = []
    latest_event_bindings: dict[str, str] = {}
    observed_fact_ids: set[str] = set()
    observed_information_bindings: dict[str, str] = {}
    hypothesis_seed_bindings: dict[str, str] = {}
    context_bindings: dict[str, str] = {}

    def bind(
        catalog: dict[str, str], *, ref: str, document: Mapping[str, Any]
    ) -> None:
        digest = canonical_digest(document)
        previous = catalog.get(ref)
        if previous is not None and previous != digest:
            raise V31ResearchCycleError("V31_INFORMATION_REFERENCE_COLLISION")
        catalog[ref] = digest
    previous_latest = {
        str(row["event_id"]): dict(row)
        for row in (
            ()
            if previous_information_revision_registry is None
            else previous_information_revision_registry.get(
                "latest_revisions", ()
            )
        )
        if isinstance(row, Mapping)
    }
    for event_id, rows in sorted(grouped.items()):
        prior = None
        for admission in sorted(rows, key=lambda row: row.event.revision):
            if prior is None and admission.event.revision > 1:
                # The cumulative registry, rebuilt immediately before this
                # helper runs, is the exact cross-cycle predecessor witness.
                # It retains the latest digest/revision/time even if this ID
                # was absent from one or more current-inference snapshots.
                prior_metadata = previous_latest.get(event_id)
                if (
                    prior_metadata is None
                    or admission.event.revision
                    != prior_metadata.get("revision", 0) + 1
                    or admission.event.previous_revision_digest
                    != prior_metadata.get("event_digest")
                ):
                    raise V31ResearchCycleError(
                        "V31_INFORMATION_CROSS_CYCLE_REVISION_INVALID"
                    )
                checked = admission
            else:
                checked = admit_information_event(
                    admission.event,
                    decision_at=decision_at,
                    prior_revision=prior,
                )
            if checked.information_event_digest != admission.information_event_digest:
                raise V31ResearchCycleError("V31_INFORMATION_ADMISSION_DIGEST_MISMATCH")
            canonical = information_event_to_canonical_dict(admission.event)
            if canonical_digest(canonical) != admission.information_event_digest:
                raise V31ResearchCycleError("V31_INFORMATION_ADMISSION_NOT_CANONICAL")
            digests.append(admission.information_event_digest)
            prior = admission.event
            latest_event_bindings[event_id] = admission.information_event_digest
        if not rows or rows[0].event.event_id != event_id:  # pragma: no cover
            raise V31ResearchCycleError("V31_INFORMATION_ADMISSION_INVALID")
        # Historical revisions remain in the sealed input receipt for audit, but
        # only the latest point-in-time revision is eligible for inference.
        # Otherwise a superseded fact or intent interpretation could be selected
        # merely by citing its old identifier or digest.
        assert prior is not None
        observed_fact_ids.update(fact.fact_id for fact in prior.observed_facts)
        # The event digest is an exact input-boundary binding, not semantic
        # evidence: it contains observed facts, actor context, intent guesses,
        # and behavior hypotheses in one aggregate.  Exposing it as evidence
        # would allow a lower epistemic class to be laundered through the
        # composite hash.
        source_bindings: dict[str, str] = {}
        for row in canonical["source_artifacts"]:
            bind(
                observed_information_bindings,
                ref=str(row["artifact_id"]),
                document=row,
            )
            source_bindings[str(row["artifact_id"])] = (
                observed_information_bindings[str(row["artifact_id"])]
            )
        fact_bindings: dict[str, str] = {}
        for row in canonical["observed_facts"]:
            bound_sources = {
                str(ref): source_bindings[str(ref)]
                for ref in row["source_artifact_ids"]
            }
            bind(
                observed_information_bindings,
                ref=str(row["fact_id"]),
                document={
                    "observed_fact": row,
                    "source_artifact_bindings": bound_sources,
                },
            )
            fact_bindings[str(row["fact_id"])] = (
                observed_information_bindings[str(row["fact_id"])]
            )
        for rows, id_field in (
            (canonical["actors"], "actor_id"),
            (canonical["actor_role_assignments"], "assignment_id"),
            (canonical["audiences"], "segment_id"),
        ):
            for row in rows:
                bind(context_bindings, ref=str(row[id_field]), document=row)
        observed_event_bindings = _merge_exact_bindings(
            source_bindings,
            fact_bindings,
            code="V31_INFORMATION_OBSERVED_BINDING_COLLISION",
        )
        intent_bindings: dict[str, str] = {}
        for row in canonical["intent_hypotheses"]:
            evidence_bindings = {
                str(ref): observed_event_bindings[str(ref)]
                for ref in row["evidence_refs"]
            }
            bind(
                hypothesis_seed_bindings,
                ref=str(row["inference_id"]),
                document={
                    "intent_hypothesis": row,
                    "subject_actor_binding": context_bindings[
                        str(row["subject_actor_id"])
                    ],
                    "evidence_bindings": evidence_bindings,
                },
            )
            intent_bindings[str(row["inference_id"])] = (
                hypothesis_seed_bindings[str(row["inference_id"])]
            )
        behavior_evidence_catalog = _merge_exact_bindings(
            observed_event_bindings,
            intent_bindings,
            code="V31_INFORMATION_BEHAVIOR_BINDING_COLLISION",
        )
        for row in canonical["behavior_response_hypotheses"]:
            evidence_bindings = {
                str(ref): behavior_evidence_catalog[str(ref)]
                for ref in row["evidence_refs"]
            }
            bind(
                hypothesis_seed_bindings,
                ref=str(row["hypothesis_id"]),
                document={
                    "behavior_response_hypothesis": row,
                    "audience_bindings": {
                        str(ref): context_bindings[str(ref)]
                        for ref in row["audience_segment_ids"]
                    },
                    "trigger_fact_bindings": {
                        str(ref): fact_bindings[str(ref)]
                        for ref in row["trigger_fact_ids"]
                    },
                    "evidence_bindings": evidence_bindings,
                },
            )
    if len(digests) != len(set(digests)):
        raise V31ResearchCycleError("V31_INFORMATION_ADMISSION_DUPLICATE")
    return (
        sorted(digests),
        latest_event_bindings,
        observed_fact_ids,
        observed_information_bindings,
        hypothesis_seed_bindings,
        context_bindings,
    )


def _verify_pit_dataset(
    dataset: Mapping[str, Any],
    *,
    decision_at: datetime,
    previous_dataset: Mapping[str, Any] | None = None,
    previous_datum_revision_registry: Mapping[str, Any] | None = None,
) -> tuple[
    str,
    set[str],
    dict[str, str],
    dict[str, str],
    dict[str, str],
    set[str],
    dict[str, PointInTimeDatum],
    set[str],
    set[str],
]:
    prior_rows: tuple[PointInTimeDatum, ...] = ()
    if previous_dataset is not None:
        try:
            point_in_time_dataset_rows_from_document(previous_dataset)
        except DataModelError as exc:
            raise V31ResearchCycleError(
                f"V31_PRIOR_PIT_DATASET_INVALID:{exc}"
            ) from exc
        if _canonical_timestamp(
            previous_dataset.get("decision_at"), "V31_PRIOR_DATASET_TIME_INVALID"
        ) >= decision_at:
            raise V31ResearchCycleError("V31_PRIOR_DATASET_TIME_INVALID")
    if previous_datum_revision_registry is not None:
        try:
            prior_rows = tuple(
                point_in_time_datum_from_document(row)
                for row in previous_datum_revision_registry.get(
                    "latest_revisions", ()
                )
            )
        except (AttributeError, DataModelError, TypeError) as exc:
            raise V31ResearchCycleError(
                "V31_PRIOR_DATUM_REVISION_REGISTRY_INVALID"
            ) from exc
    prior_revisions = {row.datum_id: row for row in prior_rows}
    try:
        rows = verify_point_in_time_dataset(
            dataset,
            prior_revisions=prior_revisions,
            external_inputs=prior_revisions,
        )
    except DataModelError as exc:
        message = str(exc)
        if "FUTURE_INFORMATION" in message:
            raise V31ResearchCycleError("V31_PIT_DATUM_FROM_FUTURE") from exc
        if "DERIVED_INPUT" in message:
            raise V31ResearchCycleError(
                "V31_PIT_DERIVED_INPUT_BINDING_INVALID"
            ) from exc
        raise V31ResearchCycleError(f"V31_PIT_DATASET_INVALID:{exc}") from exc
    if _canonical_timestamp(
        dataset.get("decision_at"), "V31_DATASET_TIME_INVALID"
    ) != decision_at:
        raise V31ResearchCycleError("V31_PIT_DATASET_BOUNDARY_INVALID")
    digest = str(dataset["dataset_digest"])
    rows_by_id = {row.datum_id: row for row in rows}
    datum_ids = set(rows_by_id)
    datum_bindings = {
        row.datum_id: row.to_document()["datum_digest"] for row in rows
    }
    fact_bindings = {
        row.datum_id: datum_bindings[row.datum_id]
        for row in rows
        if row.epistemic_type is DatumEpistemicType.OBSERVED_FACT
    }
    measure_bindings = {
        row.datum_id: datum_bindings[row.datum_id]
        for row in rows
        if row.epistemic_type is DatumEpistemicType.DERIVED_MEASURE
    }
    event_ids = {event_id for row in rows for event_id in row.event_ids}
    admissible_ids = {
        row.datum_id
        for row in rows
        if row.to_document()["inference_admissible"] is True
    }
    hypothesis_admissible_ids = {
        row.datum_id
        for row in rows
        if row.to_document()["hypothesis_admissible"] is True
    }
    if not fact_bindings or not measure_bindings:
        raise V31ResearchCycleError("V31_PIT_DATASET_TYPES_INCOMPLETE")
    return (
        digest,
        datum_ids,
        datum_bindings,
        fact_bindings,
        measure_bindings,
        event_ids,
        rows_by_id,
        admissible_ids,
        hypothesis_admissible_ids,
    )


def _verify_association_estimation_receipts(
    receipts: Sequence[Mapping[str, Any]], *, decision_at: datetime
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    if isinstance(receipts, (str, bytes)) or not isinstance(
        receipts, (list, tuple)
    ):
        raise V31ResearchCycleError("V31_ASSOCIATION_RECEIPTS_INVALID")
    digests: list[str] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        try:
            digest = verify_pearson_association_receipt(receipt)
        except AssociationEstimationError as exc:
            raise V31ResearchCycleError(
                f"V31_ASSOCIATION_RECEIPT_INVALID:{exc}"
            ) from exc
        association_id = str(receipt.get("association_id") or "")
        if (
            not association_id
            or association_id in by_id
            or _canonical_timestamp(
                receipt.get("decision_at"),
                "V31_ASSOCIATION_RECEIPT_TIME_INVALID",
            )
            > decision_at
            or _canonical_timestamp(
                receipt.get("available_at"),
                "V31_ASSOCIATION_RECEIPT_TIME_INVALID",
            )
            > decision_at
            or receipt.get("interpretation_boundary")
            != "ASSOCIATIONAL_NOT_CAUSAL"
        ):
            raise V31ResearchCycleError("V31_ASSOCIATION_RECEIPT_INVALID")
        digests.append(digest)
        by_id[association_id] = receipt
    if len(digests) != len(set(digests)):
        raise V31ResearchCycleError("V31_ASSOCIATION_RECEIPT_DUPLICATE")
    return sorted(digests), by_id


def _verify_sentiment_chain(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    symbol: str,
    market_information_snapshot: Mapping[str, Any],
    sentiment_dimension_inputs: Sequence[Mapping[str, Any]],
    sentiment_state: Mapping[str, Any],
    sentiment_change: Mapping[str, Any],
    previous_sentiment_state: Mapping[str, Any] | None,
    pit_dataset_digest: str,
    pit_rows_by_id: Mapping[str, PointInTimeDatum],
    hypothesis_admissible_datum_ids: set[str],
    inference_admissible_datum_ids: set[str],
) -> tuple[str, str, str | None]:
    """Replay sentiment and close any side channel around admitted PIT data."""

    if not isinstance(market_information_snapshot, Mapping):
        raise V31ResearchCycleError("V31_SENTIMENT_MARKET_SNAPSHOT_INVALID")
    try:
        rebuilt_snapshot = build_market_information_snapshot(
            run_id=market_information_snapshot.get("run_id"),
            cycle_index=market_information_snapshot.get("cycle_index"),
            symbol=market_information_snapshot.get("symbol"),
            as_of=market_information_snapshot.get("as_of"),
            facts=market_information_snapshot.get("facts"),
        )
        if rebuilt_snapshot != dict(market_information_snapshot):
            raise DynamicResearchError("SENTIMENT_MARKET_SNAPSHOT_REPLAY_MISMATCH")
        if (
            rebuilt_snapshot["run_id"] != run_id
            or rebuilt_snapshot["cycle_index"] != cycle_index
            or rebuilt_snapshot["symbol"] != symbol
            or _canonical_timestamp(
                rebuilt_snapshot["as_of"], "V31_SENTIMENT_TIME_INVALID"
            )
            > _canonical_timestamp(decision_at, "V31_DECISION_TIME_INVALID")
        ):
            raise DynamicResearchError("SENTIMENT_IDENTITY_INVALID")
        rebuilt_legacy_sentiment = build_sentiment_state(
            market_snapshot=rebuilt_snapshot,
            dimension_inputs=sentiment_dimension_inputs,
            operational_synthesis=sentiment_state.get("operational_synthesis"),
        )
        if (
            sentiment_state.get("pit_dataset_digest") != pit_dataset_digest
            or sentiment_state.get("downstream_scope") != "PATH_ACTION"
        ):
            raise DynamicResearchError("SENTIMENT_PIT_DATASET_BINDING_INVALID")
        facts_by_id = {
            str(row["fact_id"]): row for row in rebuilt_snapshot["facts"]
        }
        contributor_fact_ids = {
            str(contributor["fact_id"])
            for dimension in rebuilt_legacy_sentiment["dimensions"]
            for contributor in dimension["contributors"]
        }
        lineage_context_ids: set[str] = set()
        lineage_frontier = list(contributor_fact_ids)
        while lineage_frontier:
            fact_id = lineage_frontier.pop()
            for lineage_ref in facts_by_id[fact_id].get("lineage", ()):
                lineage_ref = str(lineage_ref)
                if lineage_ref not in lineage_context_ids:
                    lineage_context_ids.add(lineage_ref)
                    lineage_frontier.append(lineage_ref)
        unbound_observed_fact_ids = {
            fact_id
            for fact_id, fact in facts_by_id.items()
            if fact.get("value") is not None
            and fact_id not in contributor_fact_ids
            and fact_id not in lineage_context_ids
        }
        if unbound_observed_fact_ids:
            raise DynamicResearchError(
                "SENTIMENT_UNBOUND_OBSERVED_FACT_FORBIDDEN"
            )
        for fact_id in sorted(lineage_context_ids):
            fact = facts_by_id.get(fact_id)
            datum = pit_rows_by_id.get(fact_id)
            if fact is None or datum is None:
                raise DynamicResearchError(
                    "SENTIMENT_DERIVED_LINEAGE_CONTEXT_INVALID"
                )
            datum_document = datum.to_document()
            semantic_pairs = (
                ("category", "category"),
                ("metric", "metric"),
                ("value", "value"),
                ("unit", "unit"),
                ("symbol", "instrument_id"),
                ("timeframe", "timeframe"),
                ("window", "window"),
                ("source_ref", "source_ref"),
                ("raw_ref", "raw_ref"),
                ("raw_sha256", "raw_sha256"),
                ("observed_at", "observed_at"),
                ("available_at", "available_at"),
                ("dependency_group", "dependency_group"),
            )
            expected_kind = (
                "RAW_FACT"
                if datum.epistemic_type is DatumEpistemicType.OBSERVED_FACT
                else "DERIVED_FEATURE"
            )
            if (
                fact_id not in hypothesis_admissible_datum_ids
                or fact_id not in inference_admissible_datum_ids
                or fact.get("kind") != expected_kind
                or any(
                    fact[fact_field] != datum_document[datum_field]
                    for fact_field, datum_field in semantic_pairs
                )
            ):
                raise DynamicResearchError(
                    "SENTIMENT_DERIVED_LINEAGE_CONTEXT_INVALID"
                )
        supplied_evidence = {
            str(evidence["fact_id"]): evidence
            for dimension in sentiment_state.get("dimensions", ())
            if isinstance(dimension, Mapping)
            for evidence in dimension.get("evidence", ())
            if isinstance(evidence, Mapping)
            and isinstance(evidence.get("fact_id"), str)
        }
        if set(supplied_evidence) != contributor_fact_ids:
            raise DynamicResearchError("SENTIMENT_EVIDENCE_BINDINGS_INCOMPLETE")
        sentiment_evidence_bindings: dict[str, dict[str, str]] = {}
        for fact_id in sorted(contributor_fact_ids):
            fact = facts_by_id[fact_id]
            evidence = supplied_evidence[fact_id]
            evidence_ref = str(evidence.get("evidence_ref") or "")
            datum = pit_rows_by_id.get(evidence_ref)
            if datum is None:
                raise DynamicResearchError("SENTIMENT_PIT_DATUM_BINDING_INVALID")
            datum_document = datum.to_document()
            if (
                evidence_ref not in hypothesis_admissible_datum_ids
                or evidence_ref not in inference_admissible_datum_ids
                or evidence.get("admissibility_level")
                != "INFERENCE_ADMISSIBLE"
                or evidence.get("evidence_digest")
                != datum_document["datum_digest"]
                or evidence.get("market_fact_digest")
                != canonical_digest(fact)
            ):
                raise DynamicResearchError("SENTIMENT_PIT_DATUM_BINDING_INVALID")
            semantic_pairs = (
                ("category", "category"),
                ("metric", "metric"),
                ("value", "value"),
                ("unit", "unit"),
                ("symbol", "instrument_id"),
                ("timeframe", "timeframe"),
                ("window", "window"),
                ("source_ref", "source_ref"),
                ("raw_ref", "raw_ref"),
                ("raw_sha256", "raw_sha256"),
                ("observed_at", "observed_at"),
                ("available_at", "available_at"),
                ("dependency_group", "dependency_group"),
            )
            if any(
                fact[fact_field] != datum_document[datum_field]
                for fact_field, datum_field in semantic_pairs
            ):
                raise DynamicResearchError(
                    "SENTIMENT_PIT_DATUM_SEMANTICS_MISMATCH"
                )
            expected_kind = (
                "RAW_FACT"
                if datum.epistemic_type is DatumEpistemicType.OBSERVED_FACT
                else "DERIVED_FEATURE"
            )
            if fact.get("kind") != expected_kind:
                raise DynamicResearchError(
                    "SENTIMENT_PIT_DATUM_SEMANTICS_MISMATCH"
                )
            sentiment_evidence_bindings[fact_id] = {
                "evidence_ref": evidence_ref,
                "evidence_digest": datum_document["datum_digest"],
                "admissibility_level": "INFERENCE_ADMISSIBLE",
            }
        rebuilt_sentiment = migrate_legacy_sentiment_state_to_v31(
            legacy_sentiment_state=rebuilt_legacy_sentiment,
            market_information_snapshot=rebuilt_snapshot,
            pit_dataset_digest=pit_dataset_digest,
            sentiment_evidence_bindings=sentiment_evidence_bindings,
            downstream_scope="PATH_ACTION",
            previous_v31_sentiment_state=previous_sentiment_state,
        )
        if rebuilt_sentiment != dict(sentiment_state):
            raise DynamicResearchError("SENTIMENT_STATE_REPLAY_MISMATCH")
        sentiment_digest = verify_sentiment_state(sentiment_state)
        change_digest = verify_sentiment_state_change(
            sentiment_change,
            current_sentiment_state=sentiment_state,
            previous_sentiment_state=previous_sentiment_state,
        )
    except (DynamicResearchError, TypeError) as exc:
        raise V31ResearchCycleError(f"V31_SENTIMENT_CHAIN_INVALID:{exc}") from exc
    if sentiment_change.get("changed_at") != decision_at:
        raise V31ResearchCycleError("V31_SENTIMENT_CHANGE_TIME_INVALID")
    previous_digest = (
        None
        if previous_sentiment_state is None
        else verify_sentiment_state(previous_sentiment_state)
    )
    return sentiment_digest, change_digest, previous_digest


def _trusted_graph_associations(
    *,
    associations: Sequence[Mapping[str, Any]],
    receipts_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    active_by_id = {
        str(row["association_id"]): row for row in associations
    }
    trusted: dict[str, Mapping[str, Any]] = {}
    for association_id, receipt in receipts_by_id.items():
        row = active_by_id.get(association_id)
        receipt_digest = str(receipt["association_estimation_receipt_digest"])
        estimate = receipt["estimate"]
        matching_provenance = [
            provenance
            for provenance in row.get("provenance", [])
            if provenance.get("source_digest") == receipt_digest
            and provenance.get("source_ref")
            == f"association-estimate:{association_id}"
        ] if row is not None else []
        if (
            row is None
            or row.get("association_type") != "OBSERVED_ASSOCIATION"
            or row.get("interpretation_boundary") != "ASSOCIATIONAL_NOT_CAUSAL"
            or row.get("relation") != "ASSOCIATED_WITH"
            or row.get("source_node_id") != receipt.get("source_node_id")
            or row.get("target_node_id") != receipt.get("target_node_id")
            or row.get("method") != receipt.get("method")
            or row.get("estimate_interval", {}).get("lower")
            != estimate.get("lower")
            or row.get("estimate_interval", {}).get("point")
            != estimate.get("point")
            or row.get("estimate_interval", {}).get("upper")
            != estimate.get("upper")
            or row.get("estimate_interval", {}).get("scale") != "CORRELATION"
            or row.get("window", {}).get("start_at")
            != receipt.get("window_start")
            or row.get("window", {}).get("end_at") != receipt.get("window_end")
            or row.get("window", {}).get("timeframe")
            != receipt.get("timeframe")
            or row.get("window", {}).get("sample_count")
            != receipt.get("sample_count")
            or len(matching_provenance) != 1
        ):
            raise V31ResearchCycleError(
                "V31_ASSOCIATION_RECEIPT_GRAPH_BINDING_INVALID"
            )
        trusted[association_id] = row
    return trusted


def _verify_association_observation_bindings(
    *,
    receipts_by_id: Mapping[str, Mapping[str, Any]],
    pit_rows_by_id: Mapping[str, PointInTimeDatum],
    inference_admissible_datum_ids: set[str],
) -> None:
    """Bind every numeric pair to an admitted PIT datum, not caller numbers."""

    admitted_by_digest = {
        str(row.to_document()["datum_digest"]): row.to_document()
        for datum_id, row in pit_rows_by_id.items()
        if datum_id in inference_admissible_datum_ids
    }
    for receipt in receipts_by_id.values():
        for pair in receipt.get("paired_observations", []):
            source_digest = str(pair.get("source_datum_digest") or "")
            target_digest = str(pair.get("target_datum_digest") or "")
            source = admitted_by_digest.get(source_digest)
            target = admitted_by_digest.get(target_digest)
            if (
                source is None
                or target is None
                or source_digest == target_digest
                or source.get("value_type") != "NUMERIC"
                or target.get("value_type") != "NUMERIC"
                or source.get("value") != pair.get("source_value")
                or target.get("value") != pair.get("target_value")
                or source.get("as_of") != pair.get("as_of")
                or target.get("as_of") != pair.get("as_of")
                or max(source.get("available_at"), target.get("available_at"))
                != pair.get("available_at")
            ):
                raise V31ResearchCycleError(
                    "V31_ASSOCIATION_OBSERVATION_NOT_ADMITTED"
                )


def _verify_dynamic_research_state(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    hypothesis_registry: Mapping[str, Any],
    hypothesis_deltas: Sequence[Mapping[str, Any]],
    previous_hypothesis_registry: Mapping[str, Any] | None,
    expectation_ledger: Mapping[str, Any],
    expectation_deltas: Sequence[Mapping[str, Any]],
    previous_expectation_ledger: Mapping[str, Any] | None,
    admitted_evidence_bindings: Mapping[str, str],
) -> tuple[
    str,
    str,
    str,
    dict[str, str],
    set[str],
    set[str],
    dict[str, str],
    set[str],
]:
    """Replay deterministic reducers and bind their state to this exact cycle.

    The registry and ledger self-digests alone are not treated as proof: their
    declared deltas are replayed against the exact previous artifacts.  This
    prevents a caller from changing semantic state and merely re-signing the
    edited document with another public hash.
    """

    if not isinstance(hypothesis_registry, Mapping):
        raise V31ResearchCycleError("V31_HYPOTHESIS_REGISTRY_INVALID")
    if not isinstance(expectation_ledger, Mapping):
        raise V31ResearchCycleError("V31_EXPECTATION_LEDGER_INVALID")
    if not isinstance(hypothesis_deltas, (list, tuple)) or not isinstance(
        expectation_deltas, (list, tuple)
    ):
        raise V31ResearchCycleError("V31_DYNAMIC_RESEARCH_DELTAS_INVALID")
    if not isinstance(admitted_evidence_bindings, Mapping) or any(
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or _HEX_64.fullmatch(digest) is None
        for ref, digest in admitted_evidence_bindings.items()
    ):
        raise V31ResearchCycleError("V31_ADMITTED_EVIDENCE_CATALOG_INVALID")
    if (cycle_index == 1) != (previous_hypothesis_registry is None):
        raise V31ResearchCycleError("V31_HYPOTHESIS_CYCLE_PREDECESSOR_INVALID")
    if (cycle_index == 1) != (previous_expectation_ledger is None):
        raise V31ResearchCycleError("V31_EXPECTATION_CYCLE_PREDECESSOR_INVALID")
    try:
        max_active = hypothesis_registry.get("max_active_hypotheses")
        rebuilt_registry = reduce_hypothesis_registry(
            previous_registry=previous_hypothesis_registry,
            deltas=hypothesis_deltas,
            decision_at=decision_at,
            max_active_hypotheses=max_active,
        )
        registry_digest = verify_self_digest(
            hypothesis_registry, "hypothesis_registry_digest"
        )
    except DynamicResearchError as exc:
        raise V31ResearchCycleError(f"V31_HYPOTHESIS_REGISTRY_INVALID:{exc}") from exc
    except ValueError as exc:
        raise V31ResearchCycleError("V31_HYPOTHESIS_REGISTRY_DIGEST_INVALID") from exc
    if rebuilt_registry != dict(hypothesis_registry):
        raise V31ResearchCycleError("V31_HYPOTHESIS_REPLAY_MISMATCH")

    if (
        hypothesis_registry.get("schema_id") != "dynamic_hypothesis_registry"
        or hypothesis_registry.get("schema_version") != "1.0.0"
        or hypothesis_registry.get("revision") != cycle_index
        or hypothesis_registry.get("decision_at") != decision_at
        or hypothesis_registry.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or hypothesis_registry.get("executable") is not False
    ):
        raise V31ResearchCycleError("V31_HYPOTHESIS_CYCLE_BINDING_INVALID")
    if previous_hypothesis_registry is not None:
        try:
            prior_registry_digest = verify_self_digest(
                previous_hypothesis_registry, "hypothesis_registry_digest"
            )
        except ValueError as exc:
            raise V31ResearchCycleError(
                "V31_HYPOTHESIS_PRIOR_DIGEST_INVALID"
            ) from exc
        if (
            previous_hypothesis_registry.get("revision") != cycle_index - 1
            or hypothesis_registry.get("previous_hypothesis_registry_digest")
            != prior_registry_digest
            or _canonical_timestamp(
                previous_hypothesis_registry.get("decision_at"),
                "V31_HYPOTHESIS_PRIOR_TIME_INVALID",
            )
            >= _canonical_timestamp(decision_at, "V31_DECISION_TIME_INVALID")
        ):
            raise V31ResearchCycleError("V31_HYPOTHESIS_CYCLE_PREDECESSOR_INVALID")

    hypothesis_rows = hypothesis_registry.get("hypotheses")
    if not isinstance(hypothesis_rows, list):
        raise V31ResearchCycleError("V31_HYPOTHESIS_REGISTRY_INVALID")
    hypotheses = {
        str(row.get("hypothesis_id") or ""): row
        for row in hypothesis_rows
        if isinstance(row, Mapping)
    }
    if (
        len(hypotheses) != len(hypothesis_rows)
        or "" in hypotheses
        or not set(hypotheses).issubset(
            set(hypothesis_registry.get("known_hypothesis_ids", ()))
        )
    ):
        raise V31ResearchCycleError("V31_HYPOTHESIS_KNOWN_SET_INVALID")
    prior_hypotheses = {
        str(row.get("hypothesis_id") or ""): row
        for row in (
            previous_hypothesis_registry.get("hypotheses", [])
            if isinstance(previous_hypothesis_registry, Mapping)
            else []
        )
        if isinstance(row, Mapping)
    }
    for raw_delta in hypothesis_deltas:
        evidence_ids = set(raw_delta.get("evidence_ids", ()))
        evidence_bindings = raw_delta.get("evidence_bindings")
        if (
            not isinstance(evidence_bindings, Mapping)
            or set(evidence_bindings) != evidence_ids
            or any(
                admitted_evidence_bindings.get(ref) != digest
                for ref, digest in evidence_bindings.items()
            )
        ):
            raise V31ResearchCycleError(
                "V31_HYPOTHESIS_DELTA_EVIDENCE_NOT_ADMITTED"
            )
    for hypothesis_id, hypothesis in hypotheses.items():
        active_ids = set(hypothesis.get("active_evidence_ids", ()))
        active_bindings = hypothesis.get("active_evidence_bindings")
        if (
            not isinstance(active_bindings, Mapping)
            or set(active_bindings) != active_ids
            or any(
                admitted_evidence_bindings.get(ref) != digest
                for ref, digest in active_bindings.items()
            )
        ):
            raise V31ResearchCycleError(
                "V31_HYPOTHESIS_ACTIVE_EVIDENCE_NOT_ADMITTED"
            )
    active_hypothesis_ids = {
        hypothesis_id
        for hypothesis_id, row in hypotheses.items()
        if row.get("state") == "ACTIVE"
    }
    if sorted(active_hypothesis_ids) != hypothesis_registry.get(
        "active_hypothesis_ids"
    ):
        raise V31ResearchCycleError("V31_HYPOTHESIS_ACTIVE_SET_INVALID")
    nonterminal_hypothesis_ids = {
        hypothesis_id
        for hypothesis_id, row in hypotheses.items()
        if row.get("state") not in TERMINAL_HYPOTHESIS_STATES
    }
    hypothesis_bindings = {
        hypothesis_id: canonical_digest(row)
        for hypothesis_id, row in hypotheses.items()
    }

    known_hypothesis_ids = set(hypothesis_registry["known_hypothesis_ids"])
    try:
        rebuilt_ledger = reduce_expectation_ledger(
            previous_ledger=previous_expectation_ledger,
            deltas=expectation_deltas,
            decision_at=decision_at,
            valid_hypothesis_ids=sorted(known_hypothesis_ids),
        )
        ledger_digest = verify_self_digest(
            expectation_ledger, "expectation_ledger_digest"
        )
    except DynamicResearchError as exc:
        raise V31ResearchCycleError(f"V31_EXPECTATION_LEDGER_INVALID:{exc}") from exc
    except ValueError as exc:
        raise V31ResearchCycleError("V31_EXPECTATION_LEDGER_DIGEST_INVALID") from exc
    if rebuilt_ledger != dict(expectation_ledger):
        raise V31ResearchCycleError("V31_EXPECTATION_REPLAY_MISMATCH")
    if (
        expectation_ledger.get("schema_id") != "append_only_expectation_ledger"
        or expectation_ledger.get("schema_version") != "1.0.0"
        or expectation_ledger.get("revision") != cycle_index
        or expectation_ledger.get("decision_at") != decision_at
        or expectation_ledger.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or expectation_ledger.get("executable") is not False
    ):
        raise V31ResearchCycleError("V31_EXPECTATION_CYCLE_BINDING_INVALID")
    if previous_expectation_ledger is not None:
        try:
            prior_ledger_digest = verify_self_digest(
                previous_expectation_ledger, "expectation_ledger_digest"
            )
        except ValueError as exc:
            raise V31ResearchCycleError(
                "V31_EXPECTATION_PRIOR_DIGEST_INVALID"
            ) from exc
        if (
            previous_expectation_ledger.get("revision") != cycle_index - 1
            or expectation_ledger.get("previous_expectation_ledger_digest")
            != prior_ledger_digest
            or _canonical_timestamp(
                previous_expectation_ledger.get("decision_at"),
                "V31_EXPECTATION_PRIOR_TIME_INVALID",
            )
            >= _canonical_timestamp(decision_at, "V31_DECISION_TIME_INVALID")
        ):
            raise V31ResearchCycleError("V31_EXPECTATION_CYCLE_PREDECESSOR_INVALID")

    expectation_rows = expectation_ledger.get("expectations")
    if not isinstance(expectation_rows, list):
        raise V31ResearchCycleError("V31_EXPECTATION_LEDGER_INVALID")
    expectations = {
        str(row.get("expectation_id") or ""): row
        for row in expectation_rows
        if isinstance(row, Mapping)
    }
    if (
        len(expectations) != len(expectation_rows)
        or "" in expectations
        or not set(expectations).issubset(
            set(expectation_ledger.get("known_expectation_ids", ()))
        )
    ):
        raise V31ResearchCycleError("V31_EXPECTATION_KNOWN_SET_INVALID")
    prior_expectations = {
        str(row.get("expectation_id") or ""): row
        for row in (
            previous_expectation_ledger.get("expectations", [])
            if isinstance(previous_expectation_ledger, Mapping)
            else []
        )
        if isinstance(row, Mapping)
    }
    for expectation_id, expectation in expectations.items():
        hypothesis_id = expectation.get("hypothesis_id")
        if hypothesis_id not in known_hypothesis_ids:
            raise V31ResearchCycleError("V31_EXPECTATION_ORPHAN_HYPOTHESIS")
        if (
            expectation.get("status") not in TERMINAL_EXPECTATION_STATUSES
            and hypothesis_id not in nonterminal_hypothesis_ids
        ):
            raise V31ResearchCycleError(
                "V31_OPEN_EXPECTATION_TERMINAL_HYPOTHESIS"
            )
        if (
            expectation.get("status") not in TERMINAL_EXPECTATION_STATUSES
            and _canonical_timestamp(
                expectation.get("observation_deadline"),
                "V31_EXPECTATION_DEADLINE_INVALID",
            )
            <= _canonical_timestamp(decision_at, "V31_DECISION_TIME_INVALID")
        ):
            raise V31ResearchCycleError(
                "V31_EXPIRED_EXPECTATION_MUST_BE_CLOSED"
            )
        result_refs = set(expectation.get("result_evidence_refs", ()))
        result_bindings = expectation.get("result_evidence_bindings")
        if (
            not isinstance(result_bindings, Mapping)
            or set(result_bindings) != result_refs
            or any(
                admitted_evidence_bindings.get(ref) != digest
                for ref, digest in result_bindings.items()
            )
        ):
            raise V31ResearchCycleError(
                "V31_EXPECTATION_RESULT_EVIDENCE_NOT_ADMITTED"
            )
        parent = expectation.get("parent_expectation_id")
        if parent is not None and parent not in set(
            expectation_ledger.get("known_expectation_ids", ())
        ):
            raise V31ResearchCycleError("V31_EXPECTATION_ORPHAN_PARENT")
    open_expectation_ids = {
        expectation_id
        for expectation_id, row in expectations.items()
        if row.get("status") not in TERMINAL_EXPECTATION_STATUSES
    }
    if sorted(open_expectation_ids) != expectation_ledger.get(
        "open_expectation_ids"
    ):
        raise V31ResearchCycleError("V31_EXPECTATION_OPEN_SET_INVALID")
    known_expectation_ids = set(expectation_ledger["known_expectation_ids"])
    for hypothesis in hypotheses.values():
        if not set(hypothesis.get("derived_from_expectation_ids", ())).issubset(
            known_expectation_ids
        ):
            raise V31ResearchCycleError("V31_HYPOTHESIS_ORPHAN_EXPECTATION")
    expectation_bindings = {
        expectation_id: canonical_digest(row)
        for expectation_id, row in expectations.items()
    }
    lifecycle_binding_digest = canonical_digest(
        {
            "run_id": run_id,
            "cycle_index": cycle_index,
            "decision_at": decision_at,
            "hypothesis_registry_digest": registry_digest,
            "expectation_ledger_digest": ledger_digest,
        }
    )
    return (
        registry_digest,
        ledger_digest,
        lifecycle_binding_digest,
        hypothesis_bindings,
        active_hypothesis_ids,
        nonterminal_hypothesis_ids,
        expectation_bindings,
        open_expectation_ids,
    )


def _latest_active_nodes(graph: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in graph["node_history"]:
        node_id = str(row["node_id"])
        if node_id not in latest or row["revision"] > latest[node_id]["revision"]:
            latest[node_id] = row
    return {
        node_id: row for node_id, row in latest.items() if row["status"] == "ACTIVE"
    }


def _latest_active_associations(
    graph: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    latest: dict[str, Mapping[str, Any]] = {}
    for row in graph["association_history"]:
        association_id = str(row["association_id"])
        if association_id not in latest or row["revision"] > latest[association_id]["revision"]:
            latest[association_id] = row
    return tuple(row for row in latest.values() if row["status"] == "ACTIVE")


def _strict_reachable(
    *,
    nodes: Mapping[str, Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
    origins: set[str],
) -> set[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for association in associations:
        source = str(association["source_node_id"])
        target = str(association["target_node_id"])
        if source not in nodes or target not in nodes:
            continue
        source_stage = NODE_STAGE_ORDER[nodes[source]["node_type"]]
        target_stage = NODE_STAGE_ORDER[nodes[target]["node_type"]]
        relation = str(association["relation"])
        if relation == "DERIVED_FROM" and (
            source_stage,
            target_stage,
        ) == (3, 2):
            adjacency[target].append(source)
        elif relation == "CONDITIONED_BY" and source_stage == 4 and (
            target_stage in {2, 3}
        ):
            adjacency[target].append(source)
        elif (
            target_stage == source_stage + 1
            and relation in _ADVANCING_RELATIONS
        ):
            adjacency[source].append(target)
    reached = set(origins)
    queue = deque(origins)
    while queue:
        source = queue.popleft()
        for target in adjacency.get(source, []):
            if target not in reached:
                reached.add(target)
                queue.append(target)
    return reached


def _verify_vertical_graph_bindings(
    *,
    graph: Mapping[str, Any],
    information_event_bindings: Mapping[str, str],
    fact_bindings: Mapping[str, str],
    measure_bindings: Mapping[str, str],
    cloud_digest: str,
    hypothesis_bindings: Mapping[str, str],
    active_hypothesis_ids: set[str],
    nonterminal_hypothesis_ids: set[str],
    expectation_bindings: Mapping[str, str],
    open_expectation_ids: set[str],
    expectation_hypothesis_refs: Mapping[str, str],
    path_documents: Sequence[Mapping[str, Any]],
    candidate_evaluations: Sequence[Mapping[str, Any]],
    candidate_path_admissibility: Sequence[Mapping[str, Any]],
) -> None:
    nodes = _latest_active_nodes(graph)
    associations = _latest_active_associations(graph)
    node_types = {row["node_type"] for row in nodes.values()}
    if not _REQUIRED_GRAPH_TYPES.issubset(node_types) or not (
        {"MECHANISM_HYPOTHESIS", "PATH_HYPOTHESIS"} & node_types
    ):
        raise V31ResearchCycleError("V31_GRAPH_STAGE_COVERAGE_INCOMPLETE")
    for association in associations:
        source = nodes.get(str(association["source_node_id"]))
        target = nodes.get(str(association["target_node_id"]))
        if source is None or target is None:
            continue
        source_stage = NODE_STAGE_ORDER[source["node_type"]]
        target_stage = NODE_STAGE_ORDER[target["node_type"]]
        relation = str(association["relation"])
        semantic_reverse = (
            relation == "DERIVED_FROM"
            and (source_stage, target_stage) == (3, 2)
        ) or (
            relation == "CONDITIONED_BY"
            and source_stage == 4
            and target_stage in {2, 3}
        )
        if not semantic_reverse and (
            target_stage > source_stage + 1 or target_stage < source_stage
        ):
            raise V31ResearchCycleError("V31_GRAPH_STAGE_SKIP_FORBIDDEN")
        if (
            not semantic_reverse
            and target_stage == source_stage + 1
            and relation not in _RELATIONS_BY_ADJACENT_STAGE.get(
            (source_stage, target_stage), frozenset()
        )
        ):
            raise V31ResearchCycleError("V31_GRAPH_RELATION_STAGE_INCOMPATIBLE")

    origins = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "INFORMATION_EVENT"
        and information_event_bindings.get(row["payload_ref"])
        == row["payload_digest"]
    }
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in origins
    } != set(information_event_bindings.items()):
        raise V31ResearchCycleError("V31_GRAPH_INFORMATION_BINDING_INCOMPLETE")

    bound_fact_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "MARKET_FACT"
        and fact_bindings.get(row["payload_ref"]) == row["payload_digest"]
    }
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in bound_fact_nodes
    } != set(fact_bindings.items()):
        raise V31ResearchCycleError("V31_GRAPH_MARKET_FACT_BINDING_MISSING")

    bound_measure_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "DERIVED_MEASURE"
        and measure_bindings.get(row["payload_ref"]) == row["payload_digest"]
    }
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in bound_measure_nodes
    } != set(measure_bindings.items()):
        raise V31ResearchCycleError("V31_GRAPH_MEASURE_BINDING_MISSING")

    cloud_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "LATENT_STATE" and row["payload_digest"] == cloud_digest
    }
    if not cloud_nodes:
        raise V31ResearchCycleError("V31_GRAPH_CLOUD_BINDING_MISSING")

    required_hypothesis_refs = {
        str(reference)
        for path in path_documents
        for reference in path["mechanism_hypothesis_refs"]
    }
    required_hypothesis_refs.update(
        str(component_id)
        for path in path_documents
        for component_id in (path["path_id"],)
        if component_id in active_hypothesis_ids
    )
    hypothesis_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] in {"MECHANISM_HYPOTHESIS", "PATH_HYPOTHESIS"}
        and hypothesis_bindings.get(row["payload_ref"]) == row["payload_digest"]
    }
    declared_hypothesis_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] in {"MECHANISM_HYPOTHESIS", "PATH_HYPOTHESIS"}
    }
    if hypothesis_nodes != declared_hypothesis_nodes:
        raise V31ResearchCycleError("V31_GRAPH_HYPOTHESIS_BINDING_INVALID")
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in hypothesis_nodes
    } != {
        (hypothesis_id, hypothesis_bindings[hypothesis_id])
        for hypothesis_id in nonterminal_hypothesis_ids
    }:
        raise V31ResearchCycleError("V31_GRAPH_HYPOTHESIS_BINDING_INCOMPLETE")
    if not required_hypothesis_refs.issubset(active_hypothesis_ids):
        raise V31ResearchCycleError("V31_GRAPH_HYPOTHESIS_NOT_ACTIVE")

    expectation_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "EXPECTATION"
        and expectation_bindings.get(row["payload_ref"]) == row["payload_digest"]
    }
    declared_expectation_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "EXPECTATION"
    }
    if expectation_nodes != declared_expectation_nodes:
        raise V31ResearchCycleError("V31_GRAPH_EXPECTATION_BINDING_INVALID")
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in expectation_nodes
    } != {
        (expectation_id, expectation_bindings[expectation_id])
        for expectation_id in open_expectation_ids
    }:
        raise V31ResearchCycleError("V31_GRAPH_EXPECTATION_BINDING_INCOMPLETE")

    path_by_id = {str(row["path_id"]): row for row in path_documents}
    required_path_pairs = {
        (path_id, str(row["path_digest"])) for path_id, row in path_by_id.items()
    }
    path_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "SCENARIO_PATH"
        and (row["payload_ref"], row["payload_digest"]) in required_path_pairs
    }
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in path_nodes
    } != required_path_pairs:
        raise V31ResearchCycleError("V31_GRAPH_SCENARIO_BINDING_INCOMPLETE")

    candidate_by_id = {
        str(row["candidate_id"]): row for row in candidate_evaluations
    }
    required_candidate_pairs = {
        (candidate_id, str(row["candidate_binding_digest"]))
        for candidate_id, row in candidate_by_id.items()
    }
    action_nodes = {
        node_id
        for node_id, row in nodes.items()
        if row["node_type"] == "ACTION_CANDIDATE"
        and (row["payload_ref"], row["payload_digest"])
        in required_candidate_pairs
    }
    if {
        (nodes[node_id]["payload_ref"], nodes[node_id]["payload_digest"])
        for node_id in action_nodes
    } != required_candidate_pairs:
        raise V31ResearchCycleError("V31_GRAPH_ACTION_BINDING_INCOMPLETE")

    active_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in associations:
        active_edges[
            (str(row["source_node_id"]), str(row["target_node_id"]))
        ].add(str(row["relation"]))
    expected_observation_ids = {
        str(observation["observation_id"])
        for path in path_documents
        for observation in path["expect_by_horizon"]
    }
    if expected_observation_ids != open_expectation_ids:
        raise V31ResearchCycleError("V31_GRAPH_OPEN_EXPECTATION_COVERAGE_INVALID")
    hypothesis_node_by_ref = {
        str(nodes[node_id]["payload_ref"]): node_id for node_id in hypothesis_nodes
    }
    expectation_node_by_ref = {
        str(nodes[node_id]["payload_ref"]): node_id for node_id in expectation_nodes
    }
    for expectation_id in open_expectation_ids:
        hypothesis_id = expectation_hypothesis_refs[expectation_id]
        if (
            hypothesis_id not in hypothesis_node_by_ref
            or (
                hypothesis_node_by_ref[hypothesis_id],
                expectation_node_by_ref[expectation_id],
            )
            not in active_edges
            or not active_edges[
                (
                    hypothesis_node_by_ref[hypothesis_id],
                    expectation_node_by_ref[expectation_id],
                )
            ]
            & {"PRODUCES", "INSTANTIATES"}
        ):
            raise V31ResearchCycleError(
                "V31_GRAPH_HYPOTHESIS_EXPECTATION_BINDING_BROKEN"
            )
    for path_node_id in path_nodes:
        path = path_by_id[str(nodes[path_node_id]["payload_ref"])]
        permitted_expectations = {
            expectation_node_by_ref[str(observation["observation_id"])]
            for observation in path["expect_by_horizon"]
        }
        if not permitted_expectations or not all(
            active_edges.get((expectation_node_id, path_node_id), set())
            & {"INSTANTIATES", "TRIGGERS"}
            for expectation_node_id in permitted_expectations
        ):
            raise V31ResearchCycleError("V31_GRAPH_EXPECTATION_PATH_BINDING_BROKEN")
    admissibility_by_candidate = {
        str(row["candidate_id"]): row for row in candidate_path_admissibility
    }
    if set(admissibility_by_candidate) != set(candidate_by_id):
        raise V31ResearchCycleError("V31_CANDIDATE_PATH_ADMISSIBILITY_INCOMPLETE")
    path_node_by_ref = {
        str(nodes[node_id]["payload_ref"]): node_id for node_id in path_nodes
    }
    for action_node_id in action_nodes:
        candidate = candidate_by_id[str(nodes[action_node_id]["payload_ref"])]
        assessment = admissibility_by_candidate[candidate["candidate_id"]]
        permitted_path_refs = set(candidate["path_refs"]) | set(
            candidate["scenario_refs"]
        )
        if permitted_path_refs != {
            str(row["path_id"]) for row in assessment["path_assessments"]
        }:
            raise V31ResearchCycleError(
                "V31_GRAPH_PATH_ACTION_ADMISSIBILITY_MISMATCH"
            )
        positive_edge_found = False
        for path_assessment in assessment["path_assessments"]:
            path_node_id = path_node_by_ref[path_assessment["path_id"]]
            relations = active_edges.get((path_node_id, action_node_id), set())
            positive_relations = relations & {"SUPPORTS", "TRIGGERS"}
            if path_assessment["supports_candidate_now"]:
                if not positive_relations:
                    raise V31ResearchCycleError(
                        "V31_GRAPH_PATH_ACTION_SUPPORT_MISSING"
                    )
                positive_edge_found = True
            elif positive_relations:
                raise V31ResearchCycleError(
                    "V31_GRAPH_FALSE_OR_UNKNOWN_PATH_SUPPORT_FORBIDDEN"
                )
            if (
                path_assessment["implication_effect"] == "OPPOSES"
                and "OPPOSES" not in relations
            ):
                raise V31ResearchCycleError(
                    "V31_GRAPH_PATH_ACTION_OPPOSITION_MISSING"
                )
        if bool(assessment["selectable"]) != positive_edge_found:
            raise V31ResearchCycleError(
                "V31_GRAPH_PATH_ACTION_SELECTABILITY_MISMATCH"
            )

    reached = _strict_reachable(nodes=nodes, associations=associations, origins=origins)
    if (
        not bound_fact_nodes.issubset(reached)
        or not bound_measure_nodes.issubset(reached)
        or not cloud_nodes.issubset(reached)
        or not {
            node_id
            for node_id in hypothesis_nodes
            if nodes[node_id]["payload_ref"] in active_hypothesis_ids
        }.issubset(reached)
    ):
        raise V31ResearchCycleError("V31_GRAPH_VERTICAL_CHAIN_BROKEN")
    if (
        not {
            node_id
            for node_id in expectation_nodes
            if nodes[node_id]["payload_ref"] in open_expectation_ids
        }.issubset(reached)
        or not path_nodes.issubset(reached)
        or not {
            node_id
            for node_id in action_nodes
            if admissibility_by_candidate[
                str(nodes[node_id]["payload_ref"])
            ]["selectable"]
        }.issubset(reached)
    ):
        raise V31ResearchCycleError("V31_GRAPH_VERTICAL_CHAIN_BROKEN")


def _verify_action_evaluation(
    evaluation: Mapping[str, Any],
    *,
    context: PortfolioDecisionContext,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    probability_mode: str,
    path_ids: set[str],
    evidence_refs: set[str],
) -> tuple[str, list[Mapping[str, Any]]]:
    try:
        digest = verify_complete_action_evaluation(evaluation)
    except BehaviorPlanningError as exc:
        if "BEHAVIOR_LEGAL_ACTION_SET_INCOMPLETE" in str(exc):
            raise V31ResearchCycleError(
                "V31_ACTION_CLASS_COVERAGE_INCOMPLETE"
            ) from exc
        raise V31ResearchCycleError(
            f"V31_ACTION_EVALUATION_INVALID:{exc}"
        ) from exc
    pending_reentry_side = (
        None
        if context.pending_reentry_side is None
        else context.pending_reentry_side.value
    )
    if (
        evaluation.get("schema_id")
        != "theory_paper_v2_v31_complete_action_evaluation"
        or evaluation.get("schema_version") != "1.0.0"
        or evaluation.get("run_id") != run_id
        or evaluation.get("cycle_index") != cycle_index
        or evaluation.get("decision_at") != decision_at
        or evaluation.get("portfolio_truth_digest") != context.portfolio_truth_digest
        or evaluation.get("risk_policy_digest") != context.risk_policy_digest
        or evaluation.get("probability_mode") != probability_mode
        or evaluation.get("probability_cloud_digest")
        != context.probability_cloud_digest
        or evaluation.get("calibration_receipt_digests")
        != list(context.calibration_receipt_digests)
        or evaluation.get("proper_scoring_receipt_digests")
        != list(context.proper_scoring_receipt_digests)
        or evaluation.get("oos_evaluation_receipt_digests")
        != list(context.oos_evaluation_receipt_digests)
        or evaluation.get("position_side") != context.position_side.value
        or evaluation.get("lot_ids") != list(context.lot_ids)
        or evaluation.get("pending_reentry_side") != pending_reentry_side
        or evaluation.get("entry_scale_grid_pct")
        != list(context.entry_scale_grid_pct)
        or evaluation.get("partial_exit_scale_grid_pct")
        != list(context.partial_exit_scale_grid_pct)
        or evaluation.get("allowed_entry_roles")
        != [role.value for role in context.allowed_entry_roles]
        or _canonical_timestamp(
            evaluation.get("evaluated_at"), "V31_ACTION_EVALUATED_TIME_INVALID"
        )
        < _canonical_timestamp(decision_at, "V31_DECISION_TIME_INVALID")
        or evaluation.get("selection_present") is not False
        or evaluation.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or evaluation.get("executable") is not False
    ):
        raise V31ResearchCycleError("V31_ACTION_EVALUATION_BINDING_INVALID")
    candidates = evaluation.get("candidates")
    evaluations = evaluation.get("evaluations")
    if not isinstance(candidates, list) or not isinstance(evaluations, list) or not candidates:
        raise V31ResearchCycleError("V31_ACTION_EVALUATION_CANDIDATES_INVALID")
    candidate_ids = [str(row.get("candidate_id") or "") for row in candidates]
    evaluation_by_id = {
        str(row.get("candidate_id") or ""): row for row in evaluations
    }
    if (
        not all(candidate_ids)
        or len(candidate_ids) != len(set(candidate_ids))
        or set(candidate_ids) != set(evaluation_by_id)
    ):
        raise V31ResearchCycleError("V31_ACTION_CLASS_COVERAGE_INCOMPLETE")
    bound_rows: list[Mapping[str, Any]] = []
    for row in candidates:
        if not set(row.get("evidence_refs", [])).issubset(evidence_refs):
            raise V31ResearchCycleError("V31_ACTION_EVIDENCE_NOT_ADMITTED")
        if not set(row.get("path_refs", [])).issubset(path_ids):
            raise V31ResearchCycleError("V31_ACTION_PATH_NOT_ADMITTED")
        evaluated = evaluation_by_id[row["candidate_id"]]
        if not set(evaluated.get("scenario_refs", [])).issubset(path_ids):
            raise V31ResearchCycleError("V31_ACTION_SCENARIO_NOT_ADMITTED")
        bound_rows.append(
            {
                "candidate_id": row["candidate_id"],
                "action": row["action"],
                "candidate_proposal_digest": canonical_digest(row),
                "candidate_binding_digest": canonical_digest(
                    {"candidate": row, "evaluation": evaluated}
                ),
                "path_refs": list(row["path_refs"]),
                "scenario_refs": list(evaluated["scenario_refs"]),
                "financially_feasible": evaluated["feasible"],
            }
        )
    return digest, bound_rows


def _verify_scenario_input_bindings(
    *,
    path_documents: Sequence[Mapping[str, Any]],
    datum_bindings: Mapping[str, str],
    inference_admissible_datum_ids: set[str],
    decision_at: datetime,
) -> None:
    for path in path_documents:
        for field in ("if_triggers", "and_guards", "unless"):
            predicates = path.get(field)
            if not isinstance(predicates, list):
                raise V31ResearchCycleError("V31_SCENARIO_PREDICATES_INVALID")
            for predicate in predicates:
                if (
                    not isinstance(predicate, Mapping)
                    or predicate.get("timing") != "DECISION_INPUT"
                    or predicate.get("fact_ref")
                    not in inference_admissible_datum_ids
                    or datum_bindings.get(predicate.get("fact_ref"))
                    != predicate.get("fact_digest")
                    or _canonical_timestamp(
                        predicate.get("available_at"),
                        "V31_SCENARIO_PREDICATE_TIME_INVALID",
                    )
                    > decision_at
                ):
                    raise V31ResearchCycleError(
                        "V31_SCENARIO_DECISION_INPUT_BINDING_INVALID"
                    )
        falsifiers = path.get("falsified_when")
        if not isinstance(falsifiers, list) or not falsifiers:
            raise V31ResearchCycleError("V31_SCENARIO_FALSIFIERS_INVALID")
        for predicate in falsifiers:
            if (
                not isinstance(predicate, Mapping)
                or predicate.get("timing") != "FUTURE_MONITOR"
                or predicate.get("fact_digest") is not None
                or _canonical_timestamp(
                    predicate.get("available_at"),
                    "V31_SCENARIO_PREDICATE_TIME_INVALID",
                )
                <= decision_at
            ):
                raise V31ResearchCycleError(
                    "V31_SCENARIO_FUTURE_MONITOR_BINDING_INVALID"
                )


def _predicate_quality_for_datum(
    row: PointInTimeDatum, *, inference_admissible: bool
) -> PredicateQuality:
    if not inference_admissible:
        return PredicateQuality.UNUSABLE
    critical = (
        row.quality.source_reliability,
        row.quality.completeness,
        row.quality.timeliness,
        row.quality.semantic_fidelity,
        row.quality.lineage_integrity,
    )
    if QualityLevel.UNUSABLE in critical:
        return PredicateQuality.UNUSABLE
    if QualityLevel.UNKNOWN in critical:
        return PredicateQuality.UNKNOWN
    if QualityLevel.LOW in critical:
        return PredicateQuality.LOW
    if QualityLevel.MEDIUM in critical:
        return PredicateQuality.MEDIUM
    return PredicateQuality.HIGH


def _evaluate_scenario_path_set(
    *,
    scenario_paths: ScenarioPathSet,
    path_set_digest: str,
    pit_rows_by_id: Mapping[str, PointInTimeDatum],
    inference_admissible_datum_ids: set[str],
    decision_at: str,
) -> dict[str, Any]:
    snapshots = {
        datum_id: PathFactSnapshot(
            fact_ref=datum_id,
            fact_digest=row.to_document()["datum_digest"],
            value=row.value,
            available_at=_timestamp_text(row.available_at),
            missingness=row.missingness.value,
            quality=_predicate_quality_for_datum(
                row, inference_admissible=datum_id in inference_admissible_datum_ids
            ),
            coverage=row.coverage if row.coverage is not None else "0",
            conflict_state=row.conflict_state.value,
        )
        for datum_id, row in pit_rows_by_id.items()
    }
    snapshot_documents = [
        {
            "fact_ref": snapshot.fact_ref,
            "fact_digest": snapshot.fact_digest,
            "value": snapshot.value,
            "available_at": snapshot.available_at,
            "missingness": snapshot.missingness,
            "quality": snapshot.quality.value,
            "coverage": canonical_decimal(snapshot.coverage),
            "conflict_state": snapshot.conflict_state,
        }
        for snapshot in sorted(snapshots.values(), key=lambda item: item.fact_ref)
    ]
    try:
        results = [
            {
                "path_id": rule.path_id,
                "path_digest": rule.to_document()["path_digest"],
                "truth": evaluate_path_conditions(
                    rule, snapshots, evaluated_at=decision_at
                ).value,
            }
            for rule in scenario_paths.paths
        ]
    except ScenarioPathError as exc:
        raise V31ResearchCycleError(f"V31_PATH_EVALUATION_INVALID:{exc}") from exc
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_path_evaluation",
            "schema_version": "1.0.0",
            "decision_at": decision_at,
            "path_set_digest": path_set_digest,
            "fact_snapshot_digest": canonical_digest(snapshot_documents),
            "results": results,
            "logic": "KLEENE_THREE_VALUED_FAIL_CLOSED",
            "false_supports_action": False,
            "unknown_supports_non_wait_action": False,
            "executable": False,
        },
        "path_evaluation_digest",
    )


def _bind_candidate_path_admissibility(
    *,
    candidate_evaluations: Sequence[Mapping[str, Any]],
    path_documents: Sequence[Mapping[str, Any]],
    path_evaluation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str], str]:
    paths_by_id = {str(row["path_id"]): row for row in path_documents}
    truth_by_id = {
        str(row["path_id"]): PredicateTruth(row["truth"])
        for row in path_evaluation["results"]
    }
    rows: list[dict[str, Any]] = []
    for candidate in candidate_evaluations:
        try:
            action = ActionType(str(candidate["action"]))
        except ValueError as exc:
            raise V31ResearchCycleError("V31_ACTION_TYPE_INVALID") from exc
        path_refs = sorted(
            set(candidate["path_refs"]) | set(candidate["scenario_refs"])
        )
        if not path_refs or not set(path_refs).issubset(paths_by_id):
            raise V31ResearchCycleError("V31_ACTION_PATH_NOT_ADMITTED")
        path_assessments: list[dict[str, Any]] = []
        for path_ref in path_refs:
            implications = [
                row
                for row in paths_by_id[path_ref]["action_implications"]
                if row["action"] == action.value
            ]
            if len(implications) != 1:
                raise V31ResearchCycleError(
                    "V31_PATH_ACTION_IMPLICATION_NOT_EXACT"
                )
            effect = ImplicationEffect(implications[0]["effect"])
            truth = truth_by_id[path_ref]
            supports = (
                truth is PredicateTruth.TRUE
                and effect in {ImplicationEffect.FAVORS, ImplicationEffect.CONDITIONAL}
            ) or (
                truth is PredicateTruth.UNKNOWN
                and action in {ActionType.WAIT, ActionType.HOLD}
                and effect in {ImplicationEffect.FAVORS, ImplicationEffect.CONDITIONAL}
            )
            path_assessments.append(
                {
                    "path_id": path_ref,
                    "truth": truth.value,
                    "implication_effect": effect.value,
                    "supports_candidate_now": supports,
                }
            )
        selectable = bool(candidate["financially_feasible"]) and any(
            row["supports_candidate_now"] for row in path_assessments
        )
        reasons: list[str] = []
        if not candidate["financially_feasible"]:
            reasons.append("FINANCIALLY_INFEASIBLE")
        if not any(row["supports_candidate_now"] for row in path_assessments):
            reasons.append("NO_TRUE_OR_WAIT_COMPATIBLE_PATH_SUPPORT")
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_proposal_digest": candidate[
                    "candidate_proposal_digest"
                ],
                "candidate_binding_digest": candidate["candidate_binding_digest"],
                "action": action.value,
                "path_assessments": path_assessments,
                "selectable": selectable,
                "nonselectable_reasons": reasons,
            }
        )
    rows.sort(key=lambda row: row["candidate_id"])
    selectable_ids = [row["candidate_id"] for row in rows if row["selectable"]]
    if not selectable_ids:
        raise V31ResearchCycleError("V31_NO_SELECTABLE_ACTION_AFTER_PATH_GATE")
    digest = canonical_digest(rows)
    return rows, selectable_ids, digest


def assemble_v31_cycle_evaluation(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    symbol: str,
    information_admissions: Sequence[AdmittedInformationEvent],
    information_revision_registry: Mapping[str, Any],
    pit_dataset: Mapping[str, Any],
    datum_revision_registry: Mapping[str, Any],
    market_information_snapshot: Mapping[str, Any],
    sentiment_dimension_inputs: Sequence[Mapping[str, Any]],
    sentiment_state: Mapping[str, Any],
    sentiment_change: Mapping[str, Any],
    inputs_receipt: Mapping[str, Any],
    agent_proposal: Mapping[str, Any],
    authority_snapshot_sha256: str,
    prior_graph: Mapping[str, Any],
    graph_delta: Mapping[str, Any],
    hypothesis_registry: Mapping[str, Any],
    hypothesis_deltas: Sequence[Mapping[str, Any]],
    expectation_ledger: Mapping[str, Any],
    expectation_deltas: Sequence[Mapping[str, Any]],
    probability_cloud: ProbabilityCloud,
    scenario_paths: ScenarioPathSet,
    action_context: PortfolioDecisionContext,
    action_evaluation: Mapping[str, Any],
    previous_accepted_state_digest: str | None = None,
    previous_information_revision_registry: Mapping[str, Any] | None = None,
    previous_pit_dataset: Mapping[str, Any] | None = None,
    previous_datum_revision_registry: Mapping[str, Any] | None = None,
    previous_sentiment_state: Mapping[str, Any] | None = None,
    previous_probability_cloud: ProbabilityCloud | None = None,
    probability_cloud_transition_receipt: Mapping[str, Any] | None = None,
    previous_hypothesis_registry: Mapping[str, Any] | None = None,
    previous_expectation_ledger: Mapping[str, Any] | None = None,
    association_estimation_receipts: Sequence[Mapping[str, Any]] = (),
    selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Seal the complete V3.1 research chain before selection is admitted."""

    identity_run = _text(run_id, "V31_RUN_ID_INVALID")
    identity_symbol = _text(symbol, "V31_SYMBOL_INVALID")
    if isinstance(cycle_index, bool) or not isinstance(cycle_index, int) or cycle_index < 1:
        raise V31ResearchCycleError("V31_CYCLE_INDEX_INVALID")
    cutoff = _timestamp(decision_at, "V31_DECISION_TIME_INVALID")
    canonical_decision_at = _timestamp_text(cutoff)
    if decision_at != canonical_decision_at:
        raise V31ResearchCycleError("V31_DECISION_TIME_NOT_CANONICAL")
    if selection is not None or _contains_selection_field(action_evaluation):
        raise V31ResearchCycleError("V31_SELECTION_FORBIDDEN_BEFORE_EVALUATION_SEAL")

    (
        association_estimation_receipt_digests,
        association_receipts_by_id,
    ) = _verify_association_estimation_receipts(
        association_estimation_receipts,
        decision_at=cutoff,
    )

    try:
        rebuilt_information_registry = build_information_event_revision_registry(
            run_id=identity_run,
            cycle_index=cycle_index,
            decision_at=cutoff,
            admissions=tuple(information_admissions),
            previous_registry=previous_information_revision_registry,
        )
    except InformationModelError as exc:
        raise V31ResearchCycleError(
            f"V31_INFORMATION_REVISION_REGISTRY_INVALID:{exc}"
        ) from exc
    if rebuilt_information_registry != dict(information_revision_registry):
        raise V31ResearchCycleError(
            "V31_INFORMATION_REVISION_REGISTRY_REBUILD_MISMATCH"
        )
    information_revision_registry_digest = _digest(
        information_revision_registry.get(
            "information_revision_registry_digest"
        ),
        "V31_INFORMATION_REVISION_REGISTRY_DIGEST_INVALID",
    )

    try:
        rebuilt_datum_registry = build_point_in_time_datum_revision_registry(
            run_id=identity_run,
            cycle_index=cycle_index,
            decision_at=cutoff,
            dataset=pit_dataset,
            previous_registry=previous_datum_revision_registry,
        )
    except DataModelError as exc:
        message = str(exc)
        if "FUTURE_INFORMATION" in message:
            raise V31ResearchCycleError("V31_PIT_DATUM_FROM_FUTURE") from exc
        if "DERIVED_INPUT" in message:
            raise V31ResearchCycleError(
                "V31_PIT_DERIVED_INPUT_BINDING_INVALID"
            ) from exc
        raise V31ResearchCycleError(f"V31_PIT_DATASET_INVALID:{exc}") from exc
    if rebuilt_datum_registry != dict(datum_revision_registry):
        raise V31ResearchCycleError(
            "V31_DATUM_REVISION_REGISTRY_REBUILD_MISMATCH"
        )
    datum_revision_registry_digest = _digest(
        datum_revision_registry.get("datum_revision_registry_digest"),
        "V31_DATUM_REVISION_REGISTRY_DIGEST_INVALID",
    )

    (
        information_digests,
        latest_information_bindings,
        information_fact_ids,
        observed_information_bindings,
        hypothesis_seed_bindings,
        _information_context_bindings,
    ) = _admit_information_chain(
        information_admissions,
        decision_at=cutoff,
        previous_information_revision_registry=(
            previous_information_revision_registry
        ),
    )
    (
        dataset_digest,
        datum_ids,
        datum_bindings,
        fact_bindings,
        measure_bindings,
        dataset_event_ids,
        pit_rows_by_id,
        inference_admissible_datum_ids,
        hypothesis_admissible_datum_ids,
    ) = _verify_pit_dataset(
        pit_dataset,
        decision_at=cutoff,
        previous_dataset=previous_pit_dataset,
        previous_datum_revision_registry=previous_datum_revision_registry,
    )
    (
        sentiment_state_digest,
        sentiment_change_digest,
        verified_previous_sentiment_digest,
    ) = _verify_sentiment_chain(
        run_id=identity_run,
        cycle_index=cycle_index,
        decision_at=canonical_decision_at,
        symbol=identity_symbol,
        market_information_snapshot=market_information_snapshot,
        sentiment_dimension_inputs=sentiment_dimension_inputs,
        sentiment_state=sentiment_state,
        sentiment_change=sentiment_change,
        previous_sentiment_state=previous_sentiment_state,
        pit_dataset_digest=dataset_digest,
        pit_rows_by_id=pit_rows_by_id,
        hypothesis_admissible_datum_ids=hypothesis_admissible_datum_ids,
        inference_admissible_datum_ids=inference_admissible_datum_ids,
    )
    admitted_event_ids = {admission.event.event_id for admission in information_admissions}
    if not dataset_event_ids or not dataset_event_ids.issubset(admitted_event_ids):
        raise V31ResearchCycleError("V31_DATASET_INFORMATION_EVENT_BINDING_MISSING")
    cumulative_hypothesis_datum_bindings = {
        str(row["datum_id"]): str(row["datum_digest"])
        for row in datum_revision_registry["latest_revisions"]
        if row["hypothesis_admissible"] is True
    }
    if not hypothesis_admissible_datum_ids.issubset(
        cumulative_hypothesis_datum_bindings
    ):
        raise V31ResearchCycleError(
            "V31_HYPOTHESIS_EVIDENCE_REGISTRY_BINDING_INVALID"
        )
    admitted_research_evidence_bindings = _merge_exact_bindings(
        observed_information_bindings,
        hypothesis_seed_bindings,
        cumulative_hypothesis_datum_bindings,
        code="V31_RESEARCH_EVIDENCE_BINDING_COLLISION",
    )
    _verify_association_observation_bindings(
        receipts_by_id=association_receipts_by_id,
        pit_rows_by_id=pit_rows_by_id,
        inference_admissible_datum_ids=inference_admissible_datum_ids,
    )
    prior_graph_digest = verify_market_knowledge_graph(
        prior_graph, decision_at=canonical_decision_at
    )
    expected_previous_state_digest = (
        None
        if cycle_index == 1
        else _digest(
            previous_accepted_state_digest,
            "V31_PREVIOUS_ACCEPTED_STATE_DIGEST_REQUIRED",
        )
    )
    if cycle_index == 1 and previous_accepted_state_digest is not None:
        raise V31ResearchCycleError(
            "V31_GENESIS_PREVIOUS_ACCEPTED_STATE_FORBIDDEN"
        )
    if cycle_index == 1:
        expected_previous_dataset_digest = None
        expected_previous_information_registry_digest = None
        expected_previous_datum_registry_digest = None
        expected_previous_sentiment_digest = None
        expected_previous_registry_digest = None
        expected_previous_ledger_digest = None
        expected_previous_cloud_digest = None
        if any(
            value is not None
            for value in (
                previous_pit_dataset,
                previous_information_revision_registry,
                previous_datum_revision_registry,
                previous_sentiment_state,
                previous_hypothesis_registry,
                previous_expectation_ledger,
                previous_probability_cloud,
                probability_cloud_transition_receipt,
            )
        ):
            raise V31ResearchCycleError("V31_GENESIS_PREVIOUS_HEAD_FORBIDDEN")
    else:
        if (
            previous_pit_dataset is None
            or previous_information_revision_registry is None
            or previous_datum_revision_registry is None
            or previous_sentiment_state is None
            or previous_hypothesis_registry is None
            or previous_expectation_ledger is None
            or not isinstance(previous_probability_cloud, ProbabilityCloud)
            or probability_cloud_transition_receipt is None
        ):
            raise V31ResearchCycleError("V31_PREVIOUS_STATE_HEADS_REQUIRED")
        expected_previous_dataset_digest = _digest(
            previous_pit_dataset.get("dataset_digest"),
            "V31_PREVIOUS_DATASET_DIGEST_INVALID",
        )
        expected_previous_information_registry_digest = _digest(
            previous_information_revision_registry.get(
                "information_revision_registry_digest"
            ),
            "V31_PREVIOUS_INFORMATION_REGISTRY_DIGEST_INVALID",
        )
        expected_previous_datum_registry_digest = _digest(
            previous_datum_revision_registry.get(
                "datum_revision_registry_digest"
            ),
            "V31_PREVIOUS_DATUM_REGISTRY_DIGEST_INVALID",
        )
        expected_previous_sentiment_digest = _digest(
            verified_previous_sentiment_digest,
            "V31_PREVIOUS_SENTIMENT_DIGEST_INVALID",
        )
        expected_previous_registry_digest = _digest(
            previous_hypothesis_registry.get("hypothesis_registry_digest"),
            "V31_PREVIOUS_HYPOTHESIS_DIGEST_INVALID",
        )
        expected_previous_ledger_digest = _digest(
            previous_expectation_ledger.get("expectation_ledger_digest"),
            "V31_PREVIOUS_EXPECTATION_DIGEST_INVALID",
        )
        expected_previous_cloud_digest = previous_probability_cloud.to_document()[
            "cloud_digest"
        ]
    try:
        inputs_receipt_digest = verify_v31_inputs_receipt(inputs_receipt)
    except AgentResearchContractError as exc:
        raise V31ResearchCycleError(f"V31_INPUTS_RECEIPT_INVALID:{exc}") from exc
    if (
        inputs_receipt.get("run_id") != identity_run
        or inputs_receipt.get("cycle_index") != cycle_index
        or inputs_receipt.get("decision_at") != canonical_decision_at
        or inputs_receipt.get("symbol") != identity_symbol
        or inputs_receipt.get("information_event_digests")
        != information_digests
        or inputs_receipt.get("information_revision_registry_digest")
        != information_revision_registry_digest
        or inputs_receipt.get("association_estimation_receipt_digests")
        != association_estimation_receipt_digests
        or inputs_receipt.get("pit_dataset_digest") != dataset_digest
        or inputs_receipt.get("datum_revision_registry_digest")
        != datum_revision_registry_digest
        or inputs_receipt.get("sentiment_state_digest")
        != sentiment_state_digest
        or inputs_receipt.get("sentiment_change_digest")
        != sentiment_change_digest
        or inputs_receipt.get("prior_graph_digest") != prior_graph_digest
        or inputs_receipt.get("previous_accepted_state_digest")
        != expected_previous_state_digest
        or inputs_receipt.get("previous_pit_dataset_digest")
        != expected_previous_dataset_digest
        or inputs_receipt.get(
            "previous_information_revision_registry_digest"
        )
        != expected_previous_information_registry_digest
        or inputs_receipt.get("previous_datum_revision_registry_digest")
        != expected_previous_datum_registry_digest
        or inputs_receipt.get("previous_sentiment_state_digest")
        != expected_previous_sentiment_digest
        or inputs_receipt.get("previous_hypothesis_registry_digest")
        != expected_previous_registry_digest
        or inputs_receipt.get("previous_expectation_ledger_digest")
        != expected_previous_ledger_digest
        or inputs_receipt.get("previous_probability_cloud_digest")
        != expected_previous_cloud_digest
        or inputs_receipt.get("authority_snapshot_sha256")
        != _digest(
            authority_snapshot_sha256,
            "V31_AUTHORITY_SNAPSHOT_DIGEST_INVALID",
        )
    ):
        raise V31ResearchCycleError("V31_INPUTS_RECEIPT_BINDING_MISMATCH")
    graph_state = apply_graph_delta(
        prior_graph, graph_delta, decision_at=canonical_decision_at
    )
    graph_state_digest = verify_market_knowledge_graph(
        graph_state, decision_at=canonical_decision_at
    )
    graph_delta_digest = _verify_self(
        graph_delta, "graph_delta_digest", "V31_GRAPH_DELTA_DIGEST_INVALID"
    )
    active_graph_nodes = _latest_active_nodes(graph_state)
    active_graph_associations = _latest_active_associations(graph_state)
    trusted_graph_associations = _trusted_graph_associations(
        associations=active_graph_associations,
        receipts_by_id=association_receipts_by_id,
    )
    trusted_association_evidence_bindings: dict[str, str] = {}
    for association_id, row in trusted_graph_associations.items():
        association_digest = str(row["association_digest"])
        receipt_digest = str(
            association_receipts_by_id[association_id][
                "association_estimation_receipt_digest"
            ]
        )
        trusted_association_evidence_bindings[association_id] = (
            association_digest
        )
        trusted_association_evidence_bindings[association_digest] = (
            association_digest
        )
        trusted_association_evidence_bindings[receipt_digest] = receipt_digest
    admitted_research_evidence_bindings = _merge_exact_bindings(
        admitted_research_evidence_bindings,
        trusted_association_evidence_bindings,
        code="V31_RESEARCH_EVIDENCE_BINDING_COLLISION",
    )

    (
        hypothesis_registry_digest,
        expectation_ledger_digest,
        dynamic_research_binding_digest,
        hypothesis_bindings,
        active_hypothesis_ids,
        nonterminal_hypothesis_ids,
        expectation_bindings,
        open_expectation_ids,
    ) = _verify_dynamic_research_state(
        run_id=identity_run,
        cycle_index=cycle_index,
        decision_at=canonical_decision_at,
        hypothesis_registry=hypothesis_registry,
        hypothesis_deltas=hypothesis_deltas,
        previous_hypothesis_registry=previous_hypothesis_registry,
        expectation_ledger=expectation_ledger,
        expectation_deltas=expectation_deltas,
        previous_expectation_ledger=previous_expectation_ledger,
        admitted_evidence_bindings=admitted_research_evidence_bindings,
    )
    expectation_hypothesis_refs = {
        str(row["expectation_id"]): str(row["hypothesis_id"])
        for row in expectation_ledger["expectations"]
    }
    expectations_by_id = {
        str(row["expectation_id"]): row
        for row in expectation_ledger["expectations"]
    }

    if not isinstance(probability_cloud, ProbabilityCloud):
        raise V31ResearchCycleError("V31_PROBABILITY_CLOUD_INVALID")
    cloud_document = probability_cloud.to_document()
    cloud_digest = _verify_canonical_document_digest(
        cloud_document, "cloud_digest", "V31_PROBABILITY_CLOUD_DIGEST_INVALID"
    )
    if (
        cloud_document["decision_at"] != canonical_decision_at
        or cloud_document["expected_value_allowed"]
        is not probability_cloud.allows_expected_value
    ):
        raise V31ResearchCycleError("V31_PROBABILITY_CLOUD_DECISION_BOUNDARY_INVALID")
    # INFORMATION_EVENT nodes are composite boundary objects containing facts,
    # actor context, and psychological hypotheses.  They remain in the graph,
    # but cannot themselves become probability evidence.  Only typed observed
    # information or hypothesis seeds may enter the subjective mode below.
    admissible_low_stage_nodes = {
        node_id: row
        for node_id, row in active_graph_nodes.items()
        if (
            row["node_type"] in {"MARKET_FACT", "DERIVED_MEASURE"}
            and row["payload_ref"] in inference_admissible_datum_ids
            and datum_bindings.get(row["payload_ref"]) == row["payload_digest"]
        )
    }
    admissible_low_stage_associations = {
        str(row["association_id"]): row
        for row in active_graph_associations
        if str(row["association_id"]) in trusted_graph_associations
        and row["source_node_id"] in admissible_low_stage_nodes
        and row["target_node_id"] in admissible_low_stage_nodes
    }
    probability_information_bindings = (
        _merge_exact_bindings(
            observed_information_bindings,
            hypothesis_seed_bindings,
            code="V31_PROBABILITY_INFORMATION_BINDING_COLLISION",
        )
        if cloud_document["mode"] == "SUBJECTIVE_PLAUSIBILITY"
        else {}
    )
    admitted_probability_refs = (
        inference_admissible_datum_ids
        | set(probability_information_bindings)
        | {
            str(value)
            for row in admissible_low_stage_nodes.values()
            for value in (
                row["node_id"],
                row["payload_ref"],
                row["payload_digest"],
            )
        }
        | {
            str(value)
            for row in admissible_low_stage_associations.values()
            for value in (row["association_id"], row["association_digest"])
        }
        | {
            str(association_receipts_by_id[association_id][
                "association_estimation_receipt_digest"
            ])
            for association_id in admissible_low_stage_associations
        }
    )
    forbidden_probability_refs = {
        probability_cloud.cloud_id,
        cloud_digest,
        *active_hypothesis_ids,
        *open_expectation_ids,
    }
    for component in cloud_document["components"]:
        if (
            component["hypothesis_id"] not in {"OTHER", "UNKNOWN"}
            and component["hypothesis_id"] not in active_hypothesis_ids
        ):
            raise V31ResearchCycleError(
                "V31_PROBABILITY_CLOUD_HYPOTHESIS_NOT_REGISTERED"
            )
        for field in ("evidence_refs", "opposition_refs", "conflict_refs"):
            refs = _document_refs(
                component.get(field), "V31_PROBABILITY_CLOUD_REFS_INVALID"
            )
            if (
                set(refs) & forbidden_probability_refs
                or not set(refs).issubset(admitted_probability_refs)
            ):
                raise V31ResearchCycleError(
                    "V31_PROBABILITY_CLOUD_EVIDENCE_NOT_ADMITTED"
                )
    if cycle_index == 1:
        probability_transition = self_digest(
            {
                "schema_id": "theory_paper_v2_v31_probability_cloud_transition",
                "schema_version": "1.0.0",
                "cycle_index": cycle_index,
                "decision_at": canonical_decision_at,
                "transition_kind": "GENESIS_ADMISSION",
                "prior_cloud_digest": None,
                "updated_cloud_digest": cloud_digest,
                "transition_receipt": None,
                "transition_receipt_digest": None,
                "executable": False,
            },
            "probability_cloud_transition_digest",
        )
    else:
        assert isinstance(previous_probability_cloud, ProbabilityCloud)
        assert probability_cloud_transition_receipt is not None
        prior_component_ids = {
            component.hypothesis_id
            for component in previous_probability_cloud.components
        }
        current_component_ids = {
            component.hypothesis_id for component in probability_cloud.components
        }
        try:
            if prior_component_ids == current_component_ids:
                transition_kind = "UPDATE"
                transition_receipt_digest = verify_probability_cloud_update(
                    probability_cloud_transition_receipt,
                    prior_cloud=previous_probability_cloud,
                    updated_cloud=probability_cloud,
                )
                transition_digest_field = "update_receipt_digest"
            else:
                transition_kind = "REPARTITION"
                transition_receipt_digest = verify_probability_cloud_repartition(
                    probability_cloud_transition_receipt,
                    prior_cloud=previous_probability_cloud,
                    repartitioned_cloud=probability_cloud,
                )
                transition_digest_field = "repartition_receipt_digest"
        except ProbabilityCloudError as exc:
            raise V31ResearchCycleError(
                f"V31_PROBABILITY_CLOUD_TRANSITION_INVALID:{exc}"
            ) from exc
        admitted_probability_evidence_digests = {
            **{
                datum_id: datum_bindings[datum_id]
                for datum_id in inference_admissible_datum_ids
            },
            **probability_information_bindings,
            **{
                str(row["node_id"]): str(row["node_digest"])
                for row in admissible_low_stage_nodes.values()
            },
            **{
                association_id: str(row["association_digest"])
                for association_id, row in admissible_low_stage_associations.items()
            },
            **{
                str(association_receipts_by_id[association_id][
                    "association_estimation_receipt_digest"
                ]): str(association_receipts_by_id[association_id][
                    "association_estimation_receipt_digest"
                ])
                for association_id in admissible_low_stage_associations
            },
        }
        for evidence in probability_cloud_transition_receipt.get("evidence", []):
            if (
                admitted_probability_evidence_digests.get(
                    evidence.get("evidence_ref")
                )
                != evidence.get("evidence_digest")
            ):
                raise V31ResearchCycleError(
                    "V31_PROBABILITY_CLOUD_TRANSITION_EVIDENCE_NOT_ADMITTED"
                )
        probability_transition = self_digest(
            {
                "schema_id": "theory_paper_v2_v31_probability_cloud_transition",
                "schema_version": "1.0.0",
                "cycle_index": cycle_index,
                "decision_at": canonical_decision_at,
                "transition_kind": transition_kind,
                "prior_cloud_digest": previous_probability_cloud.to_document()[
                    "cloud_digest"
                ],
                "updated_cloud_digest": cloud_digest,
                "transition_receipt": dict(probability_cloud_transition_receipt),
                "transition_receipt_digest": probability_cloud_transition_receipt[
                    transition_digest_field
                ],
                "executable": False,
            },
            "probability_cloud_transition_digest",
        )
        if (
            probability_transition["transition_receipt_digest"]
            != transition_receipt_digest
        ):
            raise V31ResearchCycleError(
                "V31_PROBABILITY_CLOUD_TRANSITION_DIGEST_MISMATCH"
            )
    probability_cloud_transition_digest = probability_transition[
        "probability_cloud_transition_digest"
    ]

    if not isinstance(scenario_paths, ScenarioPathSet):
        raise V31ResearchCycleError("V31_SCENARIO_PATH_SET_INVALID")
    path_set_document = scenario_paths.to_document()
    path_set_digest = _verify_canonical_document_digest(
        path_set_document,
        "path_set_digest",
        "V31_SCENARIO_PATH_SET_DIGEST_INVALID",
    )
    if path_set_document["decision_at"] != canonical_decision_at:
        raise V31ResearchCycleError("V31_SCENARIO_PATH_TIME_MISMATCH")
    path_documents = path_set_document["paths"]
    for path in path_documents:
        _verify_canonical_document_digest(
            path, "path_digest", "V31_SCENARIO_PATH_DIGEST_INVALID"
        )
        if probability_cloud.cloud_id not in path["probability_cloud_refs"]:
            raise V31ResearchCycleError("V31_SCENARIO_CLOUD_BINDING_MISSING")
        mechanism_refs = set(path["mechanism_hypothesis_refs"])
        if not mechanism_refs or not mechanism_refs.issubset(
            active_hypothesis_ids
        ):
            raise V31ResearchCycleError(
                "V31_SCENARIO_HYPOTHESIS_NOT_REGISTERED"
            )
        expectation_ids = {
            str(row["observation_id"]) for row in path["expect_by_horizon"]
        }
        if not expectation_ids or not expectation_ids.issubset(open_expectation_ids):
            raise V31ResearchCycleError(
                "V31_SCENARIO_EXPECTATION_NOT_REGISTERED"
            )
        if any(
            expectation_hypothesis_refs[expectation_id] not in mechanism_refs
            for expectation_id in expectation_ids
        ):
            raise V31ResearchCycleError(
                "V31_SCENARIO_EXPECTATION_HYPOTHESIS_MISMATCH"
            )
        for observation in path["expect_by_horizon"]:
            expectation = expectations_by_id[observation["observation_id"]]
            if (
                observation.get("expectation_revision_digest")
                != expectation_bindings[expectation["expectation_id"]]
                or observation.get("hypothesis_id")
                != expectation["hypothesis_id"]
                or observation.get("horizon_at")
                != expectation["observation_deadline"]
                or not any(
                    expected.get("metric") == observation.get("observable_ref")
                    and expected.get("direction_or_range")
                    == observation.get("direction_or_state")
                    and expected.get("direction_or_range")
                    == observation.get("confirms_when")
                    for expected in expectation["expected_observations"]
                )
                or not any(
                    falsifier.get("metric") == observation.get("observable_ref")
                    and falsifier.get("direction_or_range")
                    == observation.get("contradicts_when")
                    for falsifier in expectation["falsifying_observations"]
                )
            ):
                raise V31ResearchCycleError(
                    "V31_SCENARIO_EXPECTATION_REVISION_BINDING_INVALID"
                )
    _verify_scenario_input_bindings(
        path_documents=path_documents,
        datum_bindings=datum_bindings,
        inference_admissible_datum_ids=inference_admissible_datum_ids,
        decision_at=cutoff,
    )
    path_evaluation = _evaluate_scenario_path_set(
        scenario_paths=scenario_paths,
        path_set_digest=path_set_digest,
        pit_rows_by_id=pit_rows_by_id,
        inference_admissible_datum_ids=inference_admissible_datum_ids,
        decision_at=canonical_decision_at,
    )
    path_evaluation_digest = _verify_self(
        path_evaluation,
        "path_evaluation_digest",
        "V31_PATH_EVALUATION_DIGEST_INVALID",
    )
    component_ids = {row["hypothesis_id"] for row in cloud_document["components"]}
    if not {
        scenario_paths.lead_path_id,
        scenario_paths.runner_up_path_id,
        "OTHER",
    }.issubset(component_ids):
        raise V31ResearchCycleError("V31_CLOUD_PATH_COMPETITION_INCOMPLETE")

    if not isinstance(action_context, PortfolioDecisionContext):
        raise V31ResearchCycleError("V31_ACTION_CONTEXT_INVALID")
    if (
        action_context.decision_at != canonical_decision_at
        or action_context.probability_mode.value != cloud_document["mode"]
        or action_context.probability_cloud_digest != cloud_digest
    ):
        raise V31ResearchCycleError("V31_ACTION_CONTEXT_BINDING_INVALID")
    validation_receipts = cloud_document["validation_receipts"]
    expected_calibration_digests = tuple(
        row["calibration_result_digest"] for row in validation_receipts
    )
    expected_proper_scoring_digests = tuple(
        row["proper_scoring_result_digest"] for row in validation_receipts
    )
    expected_oos_digests = tuple(
        row["oos_evaluation_digest"] for row in validation_receipts
    )
    if (
        action_context.calibration_receipt_digests
        != expected_calibration_digests
        or action_context.proper_scoring_receipt_digests
        != expected_proper_scoring_digests
        or action_context.oos_evaluation_receipt_digests != expected_oos_digests
    ):
        raise V31ResearchCycleError("V31_ACTION_CALIBRATION_BINDING_INVALID")
    admitted_evidence_refs = inference_admissible_datum_ids
    evaluation_digest, candidate_evaluations = _verify_action_evaluation(
        action_evaluation,
        context=action_context,
        run_id=identity_run,
        cycle_index=cycle_index,
        decision_at=canonical_decision_at,
        probability_mode=cloud_document["mode"],
        path_ids={row["path_id"] for row in path_documents} | {"OTHER"},
        evidence_refs=admitted_evidence_refs,
    )
    (
        candidate_path_admissibility,
        selectable_candidate_ids,
        candidate_path_admissibility_digest,
    ) = _bind_candidate_path_admissibility(
        candidate_evaluations=candidate_evaluations,
        path_documents=path_documents,
        path_evaluation=path_evaluation,
    )
    try:
        agent_proposal_digest = verify_v31_agent_proposal(
            agent_proposal, inputs_receipt=inputs_receipt
        )
    except AgentResearchContractError as exc:
        raise V31ResearchCycleError(f"V31_AGENT_PROPOSAL_INVALID:{exc}") from exc
    expected_candidate_proposal_bindings = dict(
        sorted(
            (
                str(row["candidate_id"]),
                str(row["candidate_proposal_digest"]),
            )
            for row in candidate_evaluations
        )
    )
    created_hypothesis_ids = {
        str(replacement["hypothesis_id"])
        for delta in hypothesis_deltas
        for replacement in delta.get("replacement_hypotheses", ())
        if delta.get("operation") in {"CREATE", "SPLIT", "MERGE", "SUPERSEDE"}
    }
    novelty_ids = set(agent_proposal.get("hypothesis_novelty_rationales", {}))
    if (
        agent_proposal.get("sentiment_state_digest") != sentiment_state_digest
        or agent_proposal.get("sentiment_change_digest")
        != sentiment_change_digest
        or agent_proposal.get("graph_delta_digest") != graph_delta_digest
        or agent_proposal.get("hypothesis_registry_digest")
        != hypothesis_registry_digest
        or agent_proposal.get("expectation_ledger_digest")
        != expectation_ledger_digest
        or agent_proposal.get("probability_cloud_digest") != cloud_digest
        or agent_proposal.get("scenario_path_set_digest") != path_set_digest
        or agent_proposal.get("candidate_bindings")
        != expected_candidate_proposal_bindings
        or not created_hypothesis_ids.issubset(novelty_ids)
        or not novelty_ids.issubset(set(hypothesis_bindings))
    ):
        raise V31ResearchCycleError("V31_AGENT_PROPOSAL_BINDING_MISMATCH")
    _verify_vertical_graph_bindings(
        graph=graph_state,
        information_event_bindings=latest_information_bindings,
        fact_bindings=fact_bindings,
        measure_bindings=measure_bindings,
        cloud_digest=cloud_digest,
        hypothesis_bindings=hypothesis_bindings,
        active_hypothesis_ids=active_hypothesis_ids,
        nonterminal_hypothesis_ids=nonterminal_hypothesis_ids,
        expectation_bindings=expectation_bindings,
        open_expectation_ids=open_expectation_ids,
        expectation_hypothesis_refs=expectation_hypothesis_refs,
        path_documents=path_documents,
        candidate_evaluations=candidate_evaluations,
        candidate_path_admissibility=candidate_path_admissibility,
    )

    bindings = {
        "inputs_receipt_digest": inputs_receipt_digest,
        "agent_proposal_digest": agent_proposal_digest,
        "information_event_digests": information_digests,
        "information_revision_registry_digest": (
            information_revision_registry_digest
        ),
        "association_estimation_receipt_digests": (
            association_estimation_receipt_digests
        ),
        "pit_dataset_digest": dataset_digest,
        "datum_revision_registry_digest": datum_revision_registry_digest,
        "sentiment_state_digest": sentiment_state_digest,
        "sentiment_change_digest": sentiment_change_digest,
        "prior_graph_digest": prior_graph_digest,
        "graph_delta_digest": graph_delta_digest,
        "graph_state_digest": graph_state_digest,
        "hypothesis_registry_digest": hypothesis_registry_digest,
        "expectation_ledger_digest": expectation_ledger_digest,
        "dynamic_research_binding_digest": dynamic_research_binding_digest,
        "probability_cloud_digest": cloud_digest,
        "probability_cloud_transition_digest": probability_cloud_transition_digest,
        "scenario_path_set_digest": path_set_digest,
        "path_evaluation_digest": path_evaluation_digest,
        "action_evaluation_digest": evaluation_digest,
        "candidate_path_admissibility_digest": candidate_path_admissibility_digest,
    }
    bindings_digest = canonical_digest(bindings)
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_cycle_preselection",
            "schema_version": "1.0.0",
            "run_id": identity_run,
            "cycle_index": cycle_index,
            "decision_at": canonical_decision_at,
            "symbol": identity_symbol,
            **bindings,
            "probability_cloud_transition": probability_transition,
            "path_evaluation": path_evaluation,
            "candidate_path_admissibility": candidate_path_admissibility,
            "selectable_candidate_ids": selectable_candidate_ids,
            "artifact_bindings_digest": bindings_digest,
            "binding_order": list(_BINDING_ORDER),
            "graph_chain_policy": "STRICT_ADJACENT_EPISTEMIC_STAGES",
            "selection_fields_admitted": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "preselection_digest",
    )


def verify_v31_cycle_evaluation(document: Mapping[str, Any]) -> str:
    """Verify a sealed preselection document without admitting a selection."""

    if not isinstance(document, Mapping) or set(document) != _PRESELECTION_FIELDS:
        raise V31ResearchCycleError("V31_PRESELECTION_SCHEMA_INVALID")
    digest = _verify_self(
        document, "preselection_digest", "V31_PRESELECTION_DIGEST_INVALID"
    )
    _text(document.get("run_id"), "V31_RUN_ID_INVALID")
    _text(document.get("symbol"), "V31_SYMBOL_INVALID")
    _canonical_timestamp(document.get("decision_at"), "V31_DECISION_TIME_INVALID")
    if (
        document.get("schema_id") != "theory_paper_v2_v31_cycle_preselection"
        or document.get("schema_version") != "1.0.0"
        or not isinstance(document.get("cycle_index"), int)
        or isinstance(document.get("cycle_index"), bool)
        or document.get("cycle_index", 0) < 1
        or document.get("selection_fields_admitted") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("binding_order") != list(_BINDING_ORDER)
        or document.get("graph_chain_policy")
        != "STRICT_ADJACENT_EPISTEMIC_STAGES"
    ):
        raise V31ResearchCycleError("V31_PRESELECTION_BOUNDARY_INVALID")
    bindings = {
        "inputs_receipt_digest": document["inputs_receipt_digest"],
        "agent_proposal_digest": document["agent_proposal_digest"],
        "information_event_digests": document["information_event_digests"],
        "information_revision_registry_digest": document[
            "information_revision_registry_digest"
        ],
        "association_estimation_receipt_digests": document[
            "association_estimation_receipt_digests"
        ],
        "pit_dataset_digest": document["pit_dataset_digest"],
        "datum_revision_registry_digest": document[
            "datum_revision_registry_digest"
        ],
        "sentiment_state_digest": document["sentiment_state_digest"],
        "sentiment_change_digest": document["sentiment_change_digest"],
        "prior_graph_digest": document["prior_graph_digest"],
        "graph_delta_digest": document["graph_delta_digest"],
        "graph_state_digest": document["graph_state_digest"],
        "hypothesis_registry_digest": document["hypothesis_registry_digest"],
        "expectation_ledger_digest": document["expectation_ledger_digest"],
        "dynamic_research_binding_digest": document[
            "dynamic_research_binding_digest"
        ],
        "probability_cloud_digest": document["probability_cloud_digest"],
        "probability_cloud_transition_digest": document[
            "probability_cloud_transition_digest"
        ],
        "scenario_path_set_digest": document["scenario_path_set_digest"],
        "path_evaluation_digest": document["path_evaluation_digest"],
        "action_evaluation_digest": document["action_evaluation_digest"],
        "candidate_path_admissibility_digest": document[
            "candidate_path_admissibility_digest"
        ],
    }
    if canonical_digest(bindings) != document.get("artifact_bindings_digest"):
        raise V31ResearchCycleError("V31_ARTIFACT_BINDINGS_DIGEST_INVALID")
    if canonical_digest(
        {
            "run_id": document["run_id"],
            "cycle_index": document["cycle_index"],
            "decision_at": document["decision_at"],
            "hypothesis_registry_digest": document[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": document["expectation_ledger_digest"],
        }
    ) != document["dynamic_research_binding_digest"]:
        raise V31ResearchCycleError("V31_DYNAMIC_RESEARCH_BINDING_INVALID")
    for field in (
        "inputs_receipt_digest",
        "agent_proposal_digest",
        "information_revision_registry_digest",
        "pit_dataset_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "prior_graph_digest",
        "graph_delta_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_evaluation_digest",
        "candidate_path_admissibility_digest",
        "artifact_bindings_digest",
    ):
        _digest(document.get(field), "V31_PRESELECTION_BINDING_DIGEST_INVALID")
    events = document.get("information_event_digests")
    if (
        not isinstance(events, list)
        or not events
        or len(events) != len(set(events))
        or events != sorted(events)
    ):
        raise V31ResearchCycleError("V31_PRESELECTION_INFORMATION_BINDINGS_INVALID")
    for event_digest in events:
        _digest(event_digest, "V31_PRESELECTION_INFORMATION_BINDINGS_INVALID")
    association_receipts = document.get("association_estimation_receipt_digests")
    if (
        not isinstance(association_receipts, list)
        or len(association_receipts) != len(set(association_receipts))
        or association_receipts != sorted(association_receipts)
    ):
        raise V31ResearchCycleError(
            "V31_PRESELECTION_ASSOCIATION_RECEIPTS_INVALID"
        )
    for receipt_digest in association_receipts:
        _digest(
            receipt_digest,
            "V31_PRESELECTION_ASSOCIATION_RECEIPTS_INVALID",
        )
    probability_transition = document.get("probability_cloud_transition")
    if not isinstance(probability_transition, Mapping):
        raise V31ResearchCycleError("V31_PROBABILITY_CLOUD_TRANSITION_INVALID")
    if (
        _verify_self(
            probability_transition,
            "probability_cloud_transition_digest",
            "V31_PROBABILITY_CLOUD_TRANSITION_DIGEST_INVALID",
        )
        != document["probability_cloud_transition_digest"]
        or probability_transition.get("cycle_index") != document["cycle_index"]
        or probability_transition.get("decision_at") != document["decision_at"]
        or probability_transition.get("updated_cloud_digest")
        != document["probability_cloud_digest"]
        or probability_transition.get("transition_kind")
        not in {"GENESIS_ADMISSION", "UPDATE", "REPARTITION"}
        or probability_transition.get("executable") is not False
        or (
            document["cycle_index"] == 1
            and (
                probability_transition.get("transition_kind")
                != "GENESIS_ADMISSION"
                or probability_transition.get("prior_cloud_digest") is not None
                or probability_transition.get("transition_receipt") is not None
                or probability_transition.get("transition_receipt_digest") is not None
            )
        )
        or (
            document["cycle_index"] > 1
            and (
                probability_transition.get("transition_kind")
                == "GENESIS_ADMISSION"
                or not isinstance(
                    probability_transition.get("transition_receipt"), Mapping
                )
                or _HEX_64.fullmatch(
                    str(
                        probability_transition.get(
                            "transition_receipt_digest", ""
                        )
                    )
                )
                is None
            )
        )
    ):
        raise V31ResearchCycleError(
            "V31_PROBABILITY_CLOUD_TRANSITION_BINDING_INVALID"
        )
    path_evaluation = document.get("path_evaluation")
    if not isinstance(path_evaluation, Mapping):
        raise V31ResearchCycleError("V31_PATH_EVALUATION_INVALID")
    if (
        _verify_self(
            path_evaluation,
            "path_evaluation_digest",
            "V31_PATH_EVALUATION_DIGEST_INVALID",
        )
        != document["path_evaluation_digest"]
        or path_evaluation.get("path_set_digest")
        != document["scenario_path_set_digest"]
        or path_evaluation.get("decision_at") != document["decision_at"]
        or path_evaluation.get("logic") != "KLEENE_THREE_VALUED_FAIL_CLOSED"
        or path_evaluation.get("false_supports_action") is not False
        or path_evaluation.get("unknown_supports_non_wait_action") is not False
        or path_evaluation.get("executable") is not False
    ):
        raise V31ResearchCycleError("V31_PATH_EVALUATION_BINDING_INVALID")
    admissibility = document.get("candidate_path_admissibility")
    selectable_ids = document.get("selectable_candidate_ids")
    if (
        not isinstance(admissibility, list)
        or not admissibility
        or canonical_digest(admissibility)
        != document["candidate_path_admissibility_digest"]
        or not isinstance(selectable_ids, list)
        or not selectable_ids
        or len(selectable_ids) != len(set(selectable_ids))
        or selectable_ids
        != [row.get("candidate_id") for row in admissibility if row.get("selectable")]
    ):
        raise V31ResearchCycleError(
            "V31_CANDIDATE_PATH_ADMISSIBILITY_INVALID"
        )
    return digest


def select_v31_cycle_action(
    *,
    preselection: Mapping[str, Any],
    action_evaluation: Mapping[str, Any],
    selected_candidate_id: str,
    alternative_explanations: Mapping[str, str],
    selection_rationale: str,
    failure_conditions: Sequence[str],
    next_review_at: str,
    selected_at: str,
) -> dict[str, Any]:
    """Select in a separate phase from the sealed, complete feasible set."""

    preselection_digest = verify_v31_cycle_evaluation(preselection)
    evaluation_digest = _verify_self(
        action_evaluation,
        "action_evaluation_digest",
        "V31_ACTION_EVALUATION_DIGEST_INVALID",
    )
    if evaluation_digest != preselection["action_evaluation_digest"]:
        raise V31ResearchCycleError("V31_SELECTION_EVALUATION_BINDING_MISMATCH")
    if selected_candidate_id not in preselection["selectable_candidate_ids"]:
        raise V31ResearchCycleError(
            "V31_SELECTED_CANDIDATE_NOT_PATH_ADMISSIBLE"
        )
    selection_time = _timestamp(selected_at, "V31_SELECTION_TIME_INVALID")
    decision_time = _timestamp(preselection["decision_at"], "V31_DECISION_TIME_INVALID")
    if selection_time < decision_time:
        raise V31ResearchCycleError("V31_SELECTION_PRECEDES_EVALUATION")
    proposal_digest = _digest(
        preselection["agent_proposal_digest"],
        "V31_AGENT_PROPOSAL_DIGEST_INVALID",
    )
    try:
        selection = seal_action_selection(
            evaluation=action_evaluation,
            selected_candidate_id=selected_candidate_id,
            reason=selection_rationale,
            alternative_explanations=alternative_explanations,
            failure_conditions=failure_conditions,
            next_review_at=next_review_at,
            selected_at=_timestamp_text(selection_time),
        )
    except BehaviorPlanningError as exc:
        raise V31ResearchCycleError(f"V31_SELECTION_INVALID:{exc}") from exc
    candidates = {
        row["candidate_id"]: row for row in action_evaluation.get("candidates", [])
    }
    evaluations = {
        row["candidate_id"]: row for row in action_evaluation.get("evaluations", [])
    }
    selected_binding = canonical_digest(
        {
            "candidate": candidates[selected_candidate_id],
            "evaluation": evaluations[selected_candidate_id],
        }
    )
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_accepted_research_state",
            "schema_version": "1.0.0",
            "run_id": preselection["run_id"],
            "cycle_index": preselection["cycle_index"],
            "decision_at": preselection["decision_at"],
            "selected_at": _timestamp_text(selection_time),
            "symbol": preselection["symbol"],
            "inputs_receipt_digest": preselection["inputs_receipt_digest"],
            "preselection_digest": preselection_digest,
            "artifact_bindings_digest": preselection["artifact_bindings_digest"],
            "pit_dataset_digest": preselection["pit_dataset_digest"],
            "information_revision_registry_digest": preselection[
                "information_revision_registry_digest"
            ],
            "datum_revision_registry_digest": preselection[
                "datum_revision_registry_digest"
            ],
            "sentiment_state_digest": preselection["sentiment_state_digest"],
            "sentiment_change_digest": preselection["sentiment_change_digest"],
            "graph_state_digest": preselection["graph_state_digest"],
            "hypothesis_registry_digest": preselection[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": preselection[
                "expectation_ledger_digest"
            ],
            "dynamic_research_binding_digest": preselection[
                "dynamic_research_binding_digest"
            ],
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
            "action_evaluation_digest": evaluation_digest,
            "action_selection_digest": selection["action_selection_digest"],
            "agent_proposal_digest": proposal_digest,
            "selected_candidate_id": selection["selected_candidate_id"],
            "selected_candidate_evaluation_digest": selected_binding,
            "status": "ACCEPTED_RESEARCH_ONLY",
            "selection_boundary": "SEPARATE_AFTER_COMPLETE_EVALUATION",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "accepted_state_digest",
    )


def verify_v31_accepted_state(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _ACCEPTED_FIELDS:
        raise V31ResearchCycleError("V31_ACCEPTED_STATE_SCHEMA_INVALID")
    digest = _verify_self(
        document, "accepted_state_digest", "V31_ACCEPTED_STATE_DIGEST_INVALID"
    )
    _text(document.get("run_id"), "V31_RUN_ID_INVALID")
    _text(document.get("symbol"), "V31_SYMBOL_INVALID")
    _text(
        document.get("selected_candidate_id"),
        "V31_SELECTED_CANDIDATE_ID_INVALID",
    )
    if (
        document.get("schema_id") != "theory_paper_v2_v31_accepted_research_state"
        or document.get("schema_version") != "1.0.0"
        or not isinstance(document.get("cycle_index"), int)
        or isinstance(document.get("cycle_index"), bool)
        or document.get("cycle_index", 0) < 1
        or document.get("status") != "ACCEPTED_RESEARCH_ONLY"
        or document.get("selection_boundary")
        != "SEPARATE_AFTER_COMPLETE_EVALUATION"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or _canonical_timestamp(
            document["selected_at"], "V31_SELECTION_TIME_INVALID"
        )
        < _canonical_timestamp(
            document["decision_at"], "V31_DECISION_TIME_INVALID"
        )
    ):
        raise V31ResearchCycleError("V31_ACCEPTED_STATE_BOUNDARY_INVALID")
    for field in (
        "inputs_receipt_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_evaluation_digest",
        "action_selection_digest",
        "agent_proposal_digest",
        "selected_candidate_evaluation_digest",
    ):
        _digest(document.get(field), "V31_ACCEPTED_STATE_BINDING_INVALID")
    if canonical_digest(
        {
            "run_id": document["run_id"],
            "cycle_index": document["cycle_index"],
            "decision_at": document["decision_at"],
            "hypothesis_registry_digest": document[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": document["expectation_ledger_digest"],
        }
    ) != document["dynamic_research_binding_digest"]:
        raise V31ResearchCycleError("V31_DYNAMIC_RESEARCH_BINDING_INVALID")
    return digest


def complete_v31_research_cycle(
    *, accepted_state: Mapping[str, Any], completed_at: str
) -> dict[str, Any]:
    """Seal a canonical completion receipt; this grants no execution authority."""

    accepted_digest = verify_v31_accepted_state(accepted_state)
    completion_time = _timestamp(completed_at, "V31_COMPLETION_TIME_INVALID")
    selected_time = _timestamp(
        accepted_state["selected_at"], "V31_SELECTION_TIME_INVALID"
    )
    if completion_time < selected_time:
        raise V31ResearchCycleError("V31_COMPLETION_PRECEDES_ACCEPTANCE")
    return self_digest(
        {
            "schema_id": "theory_paper_v2_v31_completion_receipt",
            "schema_version": "1.0.0",
            "run_id": accepted_state["run_id"],
            "cycle_index": accepted_state["cycle_index"],
            "decision_at": accepted_state["decision_at"],
            "selected_at": accepted_state["selected_at"],
            "completed_at": _timestamp_text(completion_time),
            "inputs_receipt_digest": accepted_state["inputs_receipt_digest"],
            "accepted_state_digest": accepted_digest,
            "preselection_digest": accepted_state["preselection_digest"],
            "artifact_bindings_digest": accepted_state["artifact_bindings_digest"],
            "pit_dataset_digest": accepted_state["pit_dataset_digest"],
            "information_revision_registry_digest": accepted_state[
                "information_revision_registry_digest"
            ],
            "datum_revision_registry_digest": accepted_state[
                "datum_revision_registry_digest"
            ],
            "sentiment_state_digest": accepted_state[
                "sentiment_state_digest"
            ],
            "sentiment_change_digest": accepted_state[
                "sentiment_change_digest"
            ],
            "graph_state_digest": accepted_state["graph_state_digest"],
            "hypothesis_registry_digest": accepted_state[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": accepted_state[
                "expectation_ledger_digest"
            ],
            "dynamic_research_binding_digest": accepted_state[
                "dynamic_research_binding_digest"
            ],
            "probability_cloud_digest": accepted_state[
                "probability_cloud_digest"
            ],
            "probability_cloud_transition_digest": accepted_state[
                "probability_cloud_transition_digest"
            ],
            "scenario_path_set_digest": accepted_state[
                "scenario_path_set_digest"
            ],
            "path_evaluation_digest": accepted_state[
                "path_evaluation_digest"
            ],
            "action_selection_digest": accepted_state["action_selection_digest"],
            "selected_candidate_id": accepted_state["selected_candidate_id"],
            "completion_status": "COMPLETE_RESEARCH_ONLY",
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        "completion_receipt_digest",
    )


def verify_v31_completion_receipt(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _COMPLETION_FIELDS:
        raise V31ResearchCycleError("V31_COMPLETION_RECEIPT_SCHEMA_INVALID")
    digest = _verify_self(
        document,
        "completion_receipt_digest",
        "V31_COMPLETION_RECEIPT_DIGEST_INVALID",
    )
    _text(document.get("run_id"), "V31_RUN_ID_INVALID")
    _text(
        document.get("selected_candidate_id"),
        "V31_SELECTED_CANDIDATE_ID_INVALID",
    )
    if (
        document.get("schema_id") != "theory_paper_v2_v31_completion_receipt"
        or document.get("schema_version") != "1.0.0"
        or not isinstance(document.get("cycle_index"), int)
        or isinstance(document.get("cycle_index"), bool)
        or document.get("cycle_index", 0) < 1
        or document.get("completion_status") != "COMPLETE_RESEARCH_ONLY"
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or _canonical_timestamp(
            document["completed_at"], "V31_COMPLETION_TIME_INVALID"
        )
        < _canonical_timestamp(
            document["selected_at"], "V31_SELECTION_TIME_INVALID"
        )
        or _canonical_timestamp(
            document["selected_at"], "V31_SELECTION_TIME_INVALID"
        )
        < _canonical_timestamp(
            document["decision_at"], "V31_DECISION_TIME_INVALID"
        )
    ):
        raise V31ResearchCycleError("V31_COMPLETION_RECEIPT_BOUNDARY_INVALID")
    for field in (
        "inputs_receipt_digest",
        "accepted_state_digest",
        "preselection_digest",
        "artifact_bindings_digest",
        "pit_dataset_digest",
        "information_revision_registry_digest",
        "datum_revision_registry_digest",
        "sentiment_state_digest",
        "sentiment_change_digest",
        "graph_state_digest",
        "hypothesis_registry_digest",
        "expectation_ledger_digest",
        "dynamic_research_binding_digest",
        "probability_cloud_digest",
        "probability_cloud_transition_digest",
        "scenario_path_set_digest",
        "path_evaluation_digest",
        "action_selection_digest",
    ):
        _digest(document.get(field), "V31_COMPLETION_RECEIPT_BINDING_INVALID")
    if canonical_digest(
        {
            "run_id": document["run_id"],
            "cycle_index": document["cycle_index"],
            "decision_at": document["decision_at"],
            "hypothesis_registry_digest": document[
                "hypothesis_registry_digest"
            ],
            "expectation_ledger_digest": document["expectation_ledger_digest"],
        }
    ) != document["dynamic_research_binding_digest"]:
        raise V31ResearchCycleError("V31_DYNAMIC_RESEARCH_BINDING_INVALID")
    return digest


__all__ = [
    "V31ResearchCycleError",
    "assemble_v31_cycle_evaluation",
    "complete_v31_research_cycle",
    "select_v31_cycle_action",
    "verify_v31_accepted_state",
    "verify_v31_completion_receipt",
    "verify_v31_cycle_evaluation",
]
