"""Production V3.1 semantic compiler for one preselection-only cycle.

The adapter reads every document through a content-addressed durable binding.
It turns the Agent's explicit semantic specifications into the existing typed
Domain objects and returns the complete input mapping replayed by Application.
It never selects an action, invents a hypothesis/path, or emits a numerical
probability.  Cycles two through eight are compiled only after all eight prior
heads and the prior graph have been independently replayed from durable state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Mapping, Protocol, Sequence

from ..application.v31_cycle_authoring import V31CycleAuthoringCompilerPort
from ..application.v31_research_cycle import verify_v31_accepted_state
from ..domain.association_estimation import verify_pearson_association_receipt
from ..domain.association_model import (
    INTERPRETATION_BOUNDARIES,
    build_association_revision,
)
from ..domain.agent_research_contract import (
    seal_v31_agent_proposal,
    seal_v31_inputs_receipt,
)
from ..domain.behavior_planning import (
    ActionCandidate,
    ActionType,
    PortfolioDecisionContext,
    PositionRole,
    PositionSide,
    action_evaluations_from_financial_receipt,
    legal_action_keys,
    seal_complete_action_evaluation,
)
from ..domain.contracts.canonical import canonical_digest, verify_self_digest
from ..domain.data_model import (
    DatumEpistemicType,
    PointInTimeDatum,
    QualityLevel,
    build_point_in_time_datum_revision_registry,
    point_in_time_datum_from_document,
    point_in_time_dataset_rows_from_document,
    verify_point_in_time_dataset,
)
from ..domain.dynamic_research import (
    MARKET_CATEGORIES,
    SENTIMENT_AXES,
    V31_SENTIMENT_AXES,
    build_market_information_snapshot,
    build_sentiment_state,
    build_sentiment_state_change,
    migrate_legacy_sentiment_state_to_v31,
    reduce_expectation_ledger,
    reduce_hypothesis_registry,
    verify_sentiment_state,
)
from ..domain.financial_evaluation import (
    build_financial_evaluation_receipt,
    build_financial_risk_policy,
)
from ..domain.governance.v31_authorization import (
    validate_v31_active_authority,
    validate_v31_theory_approval,
)
from ..domain.information_model import (
    AdmittedInformationEvent,
    InformationModelError,
    admit_information_event,
    build_information_event_revision_registry,
    information_event_from_canonical_dict,
)
from ..domain.market_knowledge_graph import (
    apply_graph_delta,
    build_graph_delta,
    build_graph_node_revision,
    create_market_knowledge_graph,
    verify_market_knowledge_graph,
)
from ..domain.portfolio_truth import build_lot_position_truth
from ..domain.probability_cloud import (
    CloudComponent,
    CloudUpdateEvidence,
    EvidenceEffect,
    PlausibilityLevel,
    ProbabilityCloud,
    ProbabilityMode,
    seal_probability_cloud_repartition,
    seal_probability_cloud_update,
)
from ..domain.scenario_path import (
    ActionImplication,
    EpistemicStage,
    EpistemicTransition,
    ExpectedObservation,
    ImplicationEffect,
    PathFactSnapshot,
    PathPredicate,
    PredicateOperator,
    PredicateQuality,
    PredicateTiming,
    PredicateTruth,
    ScenarioPathRule,
    ScenarioPathSet,
    evaluate_path_conditions,
)
from ..domain.v31_cycle_authoring import (
    validate_v31_agent_open_analysis_envelope,
    validate_v31_proposal_authoring_packet,
)
from ..domain.v31_cycle_source_admission import (
    admitted_authoring_source_bindings,
    verify_v31_cycle_source_admission,
)
from ..domain.v31_experiment_contracts import verify_minimal_experiment_contract
from ..domain.v31_source_qualification import (
    verify_v31_source_qualification_completion,
    verify_v31_source_qualification_information_event_record,
)


class V31SemanticCompilerError(ValueError):
    """A durable input or explicit Agent semantic specification failed closed."""


class V31BoundDocumentReader(Protocol):
    def read_bound_document(self, binding: Mapping[str, Any]) -> dict[str, Any]: ...

    def read_document(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str | None = None,
    ) -> dict[str, Any]: ...


_HYPOTHESIS_DELTA_FIELDS = frozenset(
    {
        "delta_id",
        "operation",
        "occurred_at",
        "target_hypothesis_ids",
        "replacement_hypotheses",
        "evidence_ids",
        "matched_hard_falsifier",
        "agent_rationale",
    }
)
_HYPOTHESIS_SPEC_FIELDS = frozenset(
    {
        "hypothesis_id",
        "revision",
        "hypothesis_type",
        "directional_bias",
        "family_label",
        "deduplication_key",
        "state",
        "parent_hypothesis_ids",
        "supersedes_ids",
        "derived_from_expectation_ids",
        "created_at",
        "updated_at",
        "horizon",
        "timeframe_scope",
        "premises",
        "expected_sequence",
        "support_rules",
        "oppose_rules",
        "hard_falsifiers",
        "expiry",
        "trade_triggers",
        "forbidden_conditions",
        "active_evidence_ids",
        "support_level",
        "limitations",
        "novelty_reason",
        "agent_rationale",
    }
)
_EXPECTATION_DELTA_FIELDS = frozenset(
    {
        "delta_id",
        "operation",
        "occurred_at",
        "target_expectation_id",
        "expectation",
        "agent_rationale",
    }
)
_EXPECTATION_SPEC_FIELDS = frozenset(
    {
        "expectation_id",
        "revision",
        "hypothesis_id",
        "parent_expectation_id",
        "deduplication_key",
        "created_at",
        "updated_at",
        "observation_start",
        "observation_deadline",
        "if_conditions",
        "expected_observations",
        "falsifying_observations",
        "evidence_sufficiency",
        "status",
        "result_evidence_refs",
        "closed_at",
        "result_note",
    }
)
_LEGACY_TO_V31 = dict(
    zip(
        SENTIMENT_AXES,
        (
            "PRICE_DIRECTIONAL_PRESSURE",
            "STRUCTURE_PERSISTENCE",
            "PARTICIPATION_AND_ACTIVE_FLOW",
            "CROWDING_DIRECTION",
            "LEVERAGE_CHANGE",
            "LIQUIDITY_RESILIENCE",
            "VOLATILITY_AND_TAIL_STRESS",
            "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
            "EVENT_AND_NARRATIVE_REACTION",
            "TIMEFRAME_COHERENCE",
        ),
    )
)
_STATE_TO_ORDINAL = {
    "STRONG_NEGATIVE": -2,
    "NEGATIVE": -1,
    "MIXED": 0,
    "NEUTRAL": 0,
    "POSITIVE": 1,
    "STRONG_POSITIVE": 2,
    "UNKNOWN": None,
}
_PREVIOUS_HEAD_CONTRACTS = {
    "previous_accepted_state": (
        "theory_paper_v2_v31_accepted_research_state",
        "accepted_state_digest",
        "accepted_state_digest",
    ),
    "previous_information_revision_registry": (
        "theory_paper_v2_v31_information_revision_registry",
        "information_revision_registry_digest",
        "information_revision_registry_digest",
    ),
    "previous_pit_dataset": (
        "theory_paper_v2_v31_point_in_time_dataset",
        "dataset_digest",
        "pit_dataset_digest",
    ),
    "previous_datum_revision_registry": (
        "theory_paper_v2_v31_datum_revision_registry",
        "datum_revision_registry_digest",
        "datum_revision_registry_digest",
    ),
    "previous_sentiment_state": (
        "theory_paper_v2_v31_multidimensional_market_sentiment_state",
        "sentiment_state_digest",
        "sentiment_state_digest",
    ),
    "previous_hypothesis_registry": (
        "dynamic_hypothesis_registry",
        "hypothesis_registry_digest",
        "hypothesis_registry_digest",
    ),
    "previous_expectation_ledger": (
        "append_only_expectation_ledger",
        "expectation_ledger_digest",
        "expectation_ledger_digest",
    ),
    "previous_probability_cloud": (
        "theory_paper_v2_v31_probability_cloud",
        "cloud_digest",
        "probability_cloud_digest",
    ),
}


def _moment(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31SemanticCompilerError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SemanticCompilerError(code) from exc
    if parsed.tzinfo is None:
        raise V31SemanticCompilerError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31SemanticCompilerError(code)
    return parsed.astimezone(UTC)


def _time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _rows(value: Any, code: str) -> list[Mapping[str, Any]]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not value
        or any(not isinstance(row, Mapping) for row in value)
    ):
        raise V31SemanticCompilerError(code)
    return list(value)


def _mapping_rows(
    value: Any, code: str, *, allow_empty: bool = False
) -> list[Mapping[str, Any]]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or (not allow_empty and not value)
        or any(not isinstance(row, Mapping) for row in value)
    ):
        raise V31SemanticCompilerError(code)
    return list(value)


def _string_rows(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V31SemanticCompilerError(code)
    rows = tuple(value)
    if (
        (not allow_empty and not rows)
        or len(rows) != len(set(rows))
        or any(not isinstance(row, str) or not row.strip() for row in rows)
    ):
        raise V31SemanticCompilerError(code)
    return tuple(rows)


def _datum_quality(row: PointInTimeDatum, *, admitted: bool) -> PredicateQuality:
    if not admitted:
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


def _probability_cloud_from_document(
    document: Mapping[str, Any],
) -> ProbabilityCloud:
    """Reconstruct the production subjective cloud with an exact round trip."""

    try:
        if (
            document.get("schema_id")
            != "theory_paper_v2_v31_probability_cloud"
            or document.get("schema_version") != "1.0.0"
            or document.get("mode") != "SUBJECTIVE_PLAUSIBILITY"
            or document.get("validation_receipts") != []
        ):
            raise ValueError("CLOUD_DOCUMENT_BOUNDARY_INVALID")
        components = tuple(
            CloudComponent(
                hypothesis_id=row["hypothesis_id"],
                plausibility=(
                    None
                    if row["plausibility"] is None
                    else PlausibilityLevel(row["plausibility"])
                ),
                lower=row["lower"],
                upper=row["upper"],
                probability=row["probability"],
                evidence_refs=tuple(row["evidence_refs"]),
                opposition_refs=tuple(row["opposition_refs"]),
                conflict_refs=tuple(row["conflict_refs"]),
                dependency_groups=tuple(row["dependency_groups"]),
                data_uncertainty=tuple(row["data_uncertainty"]),
                model_uncertainty=tuple(row["model_uncertainty"]),
                sensitivity_notes=tuple(row["sensitivity_notes"]),
            )
            for row in document["components"]
        )
        cloud = ProbabilityCloud(
            cloud_id=document["cloud_id"],
            mode=ProbabilityMode(document["mode"]),
            decision_at=document["decision_at"],
            available_at=document["available_at"],
            horizon=document["horizon"],
            components=components,
            event_contract_ref=document["event_contract_ref"],
            event_contract_digest=document["event_contract_digest"],
            sample_contract_refs=tuple(document["sample_contract_refs"]),
            model_refs=tuple(document["model_refs"]),
            market_contract_refs=tuple(document["market_contract_refs"]),
            liquidity_assumptions=tuple(document["liquidity_assumptions"]),
            risk_premium_assumptions=tuple(
                document["risk_premium_assumptions"]
            ),
            validation_receipts=(),
            unknown_refs=tuple(document["unknown_refs"]),
            limitations=tuple(document["limitations"]),
            mutually_exclusive=document["mutually_exclusive"],
            exhaustive=document["exhaustive"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V31SemanticCompilerError(
            "V31_SEMANTIC_PREVIOUS_CLOUD_INVALID"
        ) from exc
    if cloud.to_document() != dict(document):
        raise V31SemanticCompilerError(
            "V31_SEMANTIC_PREVIOUS_CLOUD_REPLAY_MISMATCH"
        )
    return cloud


class LocalV31SemanticCompiler(V31CycleAuthoringCompilerPort):
    """Content-addressed local adapter implementing the production compiler."""

    compiler_id = "LOCAL_V31_PRODUCTION_SEMANTIC_COMPILER_1_0_0"

    def __init__(self, *, store: V31BoundDocumentReader) -> None:
        self._store = store

    def _read(self, binding: Mapping[str, Any], code: str) -> dict[str, Any]:
        try:
            return self._store.read_bound_document(binding)
        except BaseException as exc:
            raise V31SemanticCompilerError(code) from exc

    def _read_relative(
        self,
        *,
        relative_ref: str,
        digest_field: str,
        expected_semantic_digest: str,
        code: str,
    ) -> dict[str, Any]:
        try:
            reader = getattr(self._store, "read_document")
            return reader(
                relative_ref=relative_ref,
                digest_field=digest_field,
                expected_semantic_digest=expected_semantic_digest,
            )
        except BaseException as exc:
            raise V31SemanticCompilerError(code) from exc

    def _load_bound_inputs(
        self, packet: Mapping[str, Any]
    ) -> dict[str, Any]:
        completion = self._read(
            packet["source_qualification_completion_binding"],
            "V31_SEMANTIC_SOURCE_COMPLETION_READ_FAILED",
        )
        try:
            verify_v31_source_qualification_completion(completion)
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_SOURCE_COMPLETION_INVALID"
            ) from exc
        dataset = self._read(
            packet["pit_dataset_binding"], "V31_SEMANTIC_DATASET_READ_FAILED"
        )
        try:
            verify_point_in_time_dataset(dataset)
        except ValueError as exc:
            raise V31SemanticCompilerError("V31_SEMANTIC_DATASET_INVALID") from exc
        if (
            dataset.get("dataset_digest")
            != packet["pit_dataset_binding"]["semantic_digest"]
            or completion.get("pit_dataset_digest") != dataset.get("dataset_digest")
            or dataset.get("decision_at") != packet["decision_at"]
        ):
            raise V31SemanticCompilerError("V31_SEMANTIC_DATASET_BINDING_MISMATCH")

        records: list[dict[str, Any]] = []
        admissions: list[AdmittedInformationEvent] = []
        decision = _moment(packet["decision_at"], "V31_SEMANTIC_DECISION_TIME_INVALID")
        for binding in packet["information_event_bindings"]:
            record = self._read(binding, "V31_SEMANTIC_INFORMATION_EVENT_READ_FAILED")
            # Historical Q6 records may be self-consistent under the retired
            # ``NONE_E0`` label.  Detect that boundary before canonical record
            # reconstruction so callers receive the specific migration error,
            # rather than an ambiguous information-record failure.
            event_document = record.get("event_document")
            if isinstance(event_document, Mapping) and (
                event_document.get("external_execution_authority") == "NONE_E0"
                or any(
                    isinstance(source, Mapping)
                    and isinstance(source.get("acquisition_receipt"), Mapping)
                    and source["acquisition_receipt"].get(
                        "external_execution_authority"
                    )
                    == "NONE_E0"
                    for source in event_document.get("source_artifacts", [])
                    if isinstance(event_document.get("source_artifacts"), list)
                )
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_LEGACY_AUTHORITY_LABEL_NOT_CYCLE_ADMISSIBLE"
                )
            try:
                verify_v31_source_qualification_information_event_record(
                    record, qualification_id=str(completion["qualification_id"])
                )
                event = information_event_from_canonical_dict(record["event_document"])
                admission = admit_information_event(event, decision_at=decision)
            except InformationModelError as exc:
                if "LEGACY_AUTHORITY_LABEL" in str(exc):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_LEGACY_AUTHORITY_LABEL_NOT_CYCLE_ADMISSIBLE"
                    ) from exc
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_INFORMATION_EVENT_INVALID"
                ) from exc
            except ValueError as exc:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_INFORMATION_EVENT_INVALID"
                ) from exc
            if (
                record.get("information_event_digest")
                != admission.information_event_digest
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_INFORMATION_EVENT_DIGEST_MISMATCH"
                )
            records.append(record)
            admissions.append(admission)
        if sorted(completion.get("information_event_digests", [])) != sorted(
            row.information_event_digest for row in admissions
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_COMPLETION_INFORMATION_BINDING_MISMATCH"
            )

        approval = self._read(
            packet["authority_context"]["theory_approval_binding"],
            "V31_SEMANTIC_THEORY_APPROVAL_READ_FAILED",
        )
        experiment = self._read(
            packet["authority_context"]["experiment_subject_binding"],
            "V31_SEMANTIC_EXPERIMENT_SUBJECT_READ_FAILED",
        )
        try:
            validate_v31_theory_approval(approval)
            verify_minimal_experiment_contract(experiment)
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_AUTHORITY_SUBJECT_INVALID"
            ) from exc
        if (
            experiment.get("run_id") != packet["run_id"]
            or experiment.get("instrument", {}).get("instrument_id")
            != packet["symbol"]
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_EXPERIMENT_IDENTITY_MISMATCH"
            )
        active_binding = packet["authority_context"]["active_authority_binding"]
        active = None
        if active_binding is not None:
            active = self._read(
                active_binding, "V31_SEMANTIC_ACTIVE_AUTHORITY_READ_FAILED"
            )
            try:
                manifest = self._read_relative(
                    relative_ref="genesis/experiment-manifest.json",
                    digest_field="manifest_digest",
                    expected_semantic_digest=str(
                        active["manifest_binding"]["semantic_digest"]
                    ),
                    code="V31_SEMANTIC_MANIFEST_READ_FAILED",
                )
                authorization = self._read_relative(
                    relative_ref="genesis/experiment-authorization.json",
                    digest_field="authorization_receipt_digest",
                    expected_semantic_digest=str(
                        active["authorization_receipt_binding"][
                            "semantic_digest"
                        ]
                    ),
                    code="V31_SEMANTIC_AUTHORIZATION_READ_FAILED",
                )
                validate_v31_active_authority(
                    active,
                    theory_approval=approval,
                    manifest=manifest,
                    experiment_contract=experiment,
                    authorization_receipt=authorization,
                )
            except ValueError as exc:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_ACTIVE_AUTHORITY_INVALID"
                ) from exc
        admission_binding = packet["cycle_source_admission_binding"]
        source_admission = None
        if admission_binding is not None:
            source_admission = self._read(
                admission_binding,
                "V31_SEMANTIC_CYCLE_SOURCE_ADMISSION_READ_FAILED",
            )
            try:
                verify_v31_cycle_source_admission(source_admission)
                projected = admitted_authoring_source_bindings(
                    source_admission
                )
            except ValueError as exc:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CYCLE_SOURCE_ADMISSION_INVALID"
                ) from exc
            if active is None or (
                source_admission.get("run_id") != packet["run_id"]
                or source_admission.get("cycle_index")
                != packet["cycle_index"]
                or source_admission.get("decision_at")
                != packet["decision_at"]
                or source_admission.get("symbol") != packet["symbol"]
                or source_admission.get("active_authority_digest")
                != active.get("authority_digest")
                or source_admission.get("experiment_contract_digest")
                != experiment.get("experiment_contract_digest")
                or source_admission.get(
                    "source_qualification_completion_digest"
                )
                != completion.get("source_qualification_completion_digest")
                or projected["source_qualification_completion_binding"]
                != packet["source_qualification_completion_binding"]
                or projected["information_event_bindings"]
                != packet["information_event_bindings"]
                or projected["pit_dataset_binding"]
                != packet["pit_dataset_binding"]
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CYCLE_SOURCE_ADMISSION_BINDING_MISMATCH"
                )
        authority_sha = (
            packet["authority_context"]["experiment_subject_binding"][
                "physical_sha256"
            ]
            if active_binding is None
            else active_binding["physical_sha256"]
        )

        associations = []
        for binding in packet["association_estimation_receipt_bindings"]:
            receipt = self._read(
                binding, "V31_SEMANTIC_ASSOCIATION_RECEIPT_READ_FAILED"
            )
            try:
                verify_pearson_association_receipt(receipt)
            except ValueError as exc:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_ASSOCIATION_RECEIPT_INVALID"
                ) from exc
            associations.append(receipt)
        return {
            "completion": completion,
            "dataset": dataset,
            "information_records": records,
            "information_admissions": admissions,
            "approval": approval,
            "experiment": experiment,
            "active_authority": active,
            "cycle_source_admission": source_admission,
            "authority_sha256": authority_sha,
            "association_receipts": associations,
        }

    def _load_previous_state(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
    ) -> dict[str, Any]:
        cycle = int(packet["cycle_index"])
        heads = packet["previous_head_bindings"]
        if cycle == 1:
            if any(value is not None for value in heads.values()):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_GENESIS_PREVIOUS_HEAD_FORBIDDEN"
                )
            return {
                "accepted": None,
                "information_registry": None,
                "pit_dataset": None,
                "datum_registry": None,
                "sentiment": None,
                "hypothesis_registry": None,
                "expectation_ledger": None,
                "cloud": None,
                "graph": None,
            }
        if cycle > 8 or any(value is None for value in heads.values()):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_HEAD_SET_INVALID"
            )
        prior_cycle = cycle - 1
        filenames = {
            "previous_accepted_state": "accepted-research-state.json",
            "previous_information_revision_registry": (
                "information-revision-registry.json"
            ),
            "previous_pit_dataset": "pit-dataset.json",
            "previous_datum_revision_registry": "datum-revision-registry.json",
            "previous_sentiment_state": "sentiment-state.json",
            "previous_hypothesis_registry": "hypothesis-registry.json",
            "previous_expectation_ledger": "expectation-ledger.json",
            "previous_probability_cloud": "probability-cloud.json",
        }
        documents: dict[str, dict[str, Any]] = {}
        for key, (schema_id, digest_field, _) in _PREVIOUS_HEAD_CONTRACTS.items():
            binding = heads[key]
            assert isinstance(binding, Mapping)
            expected_ref = f"cycles/{prior_cycle:04d}/{filenames[key]}"
            if binding.get("relative_ref") != expected_ref:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_PREVIOUS_HEAD_PATH_INVALID"
                )
            document = self._read(
                binding, "V31_SEMANTIC_PREVIOUS_HEAD_READ_FAILED"
            )
            try:
                digest = verify_self_digest(document, digest_field)
            except ValueError as exc:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_PREVIOUS_HEAD_DIGEST_INVALID"
                ) from exc
            if (
                document.get("schema_id") != schema_id
                or digest != binding.get("semantic_digest")
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_PREVIOUS_HEAD_BINDING_MISMATCH"
                )
            documents[key] = document

        accepted = documents["previous_accepted_state"]
        try:
            accepted_digest = verify_v31_accepted_state(accepted)
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_ACCEPTED_STATE_INVALID"
            ) from exc
        previous_decision = _moment(
            accepted["decision_at"],
            "V31_SEMANTIC_PREVIOUS_DECISION_TIME_INVALID",
        )
        current_decision = _moment(
            packet["decision_at"], "V31_SEMANTIC_DECISION_TIME_INVALID"
        )
        if (
            accepted.get("run_id") != packet["run_id"]
            or accepted.get("symbol") != packet["symbol"]
            or accepted.get("cycle_index") != prior_cycle
            or previous_decision >= current_decision
            or _moment(
                accepted["selected_at"],
                "V31_SEMANTIC_PREVIOUS_SELECTION_TIME_INVALID",
            )
            >= current_decision
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_ACCEPTED_STATE_IDENTITY_INVALID"
            )
        for key, (_, digest_field, accepted_field) in (
            _PREVIOUS_HEAD_CONTRACTS.items()
        ):
            document = documents[key]
            if (
                document[digest_field] != accepted[accepted_field]
                or (
                    "run_id" in document
                    and document["run_id"] != packet["run_id"]
                )
                or (
                    "cycle_index" in document
                    and document["cycle_index"] != prior_cycle
                )
                or (
                    "decision_at" in document
                    and document["decision_at"] != accepted["decision_at"]
                )
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_PREVIOUS_HEAD_ACCEPTED_BINDING_MISMATCH"
                )
        try:
            point_in_time_dataset_rows_from_document(
                documents["previous_pit_dataset"]
            )
            for row in documents["previous_datum_revision_registry"][
                "latest_revisions"
            ]:
                point_in_time_datum_from_document(row)
            verify_sentiment_state(documents["previous_sentiment_state"])
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_TYPED_HEAD_INVALID"
            ) from exc
        previous_cloud = _probability_cloud_from_document(
            documents["previous_probability_cloud"]
        )
        if previous_cloud.decision_at != accepted["decision_at"]:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_CLOUD_TIME_MISMATCH"
            )
        previous_graph = self._read_relative(
            relative_ref=f"cycles/{prior_cycle:04d}/graph-state.json",
            digest_field="graph_digest",
            expected_semantic_digest=str(accepted["graph_state_digest"]),
            code="V31_SEMANTIC_PREVIOUS_GRAPH_READ_FAILED",
        )
        try:
            verify_market_knowledge_graph(
                previous_graph, decision_at=accepted["decision_at"]
            )
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_GRAPH_INVALID"
            ) from exc
        if (
            previous_graph.get("graph_id")
            != envelope["graph_delta_spec"]["graph_id"]
            or previous_graph.get("revision") != prior_cycle
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PREVIOUS_GRAPH_IDENTITY_INVALID"
            )
        return {
            "accepted": accepted,
            "accepted_digest": accepted_digest,
            "information_registry": documents[
                "previous_information_revision_registry"
            ],
            "pit_dataset": documents["previous_pit_dataset"],
            "datum_registry": documents[
                "previous_datum_revision_registry"
            ],
            "sentiment": documents["previous_sentiment_state"],
            "hypothesis_registry": documents[
                "previous_hypothesis_registry"
            ],
            "expectation_ledger": documents[
                "previous_expectation_ledger"
            ],
            "cloud": previous_cloud,
            "graph": previous_graph,
        }

    def _sentiment(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        dataset: Mapping[str, Any],
        rows_by_id: Mapping[str, PointInTimeDatum],
        previous_sentiment_state: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        analyses = {row["axis"]: row for row in envelope["sentiment_axis_analyses"]}
        for axis in (
            "FORCED_DELEVERAGING_PRESSURE",
            "ATTENTION_AND_AUDIENCE_RESPONSE",
        ):
            if (
                analyses[axis]["ordinal_state"] != "UNKNOWN"
                or analyses[axis]["evidence_assessments"]
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_NATIVE_ONLY_SENTIMENT_AXIS_NOT_IMPLEMENTED"
                )
        selected: dict[str, PointInTimeDatum] = {}
        for axis in _LEGACY_TO_V31.values():
            for assessment in analyses[axis]["evidence_assessments"]:
                ref = assessment["evidence_ref"]
                datum = rows_by_id.get(ref)
                document = None if datum is None else datum.to_document()
                if (
                    datum is None
                    or document["inference_admissible"] is not True
                    or document["hypothesis_admissible"] is not True
                    or document["value"] is None
                    or document["raw_ref"] is None
                    or document["raw_sha256"] is None
                ):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_SENTIMENT_EVIDENCE_NOT_ADMISSIBLE"
                    )
                selected[ref] = datum

        snapshot_rows = dict(selected)
        pending = list(selected.values())
        while pending:
            datum = pending.pop()
            for input_ref in datum.input_refs:
                input_row = rows_by_id.get(input_ref)
                if input_row is None:
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_SENTIMENT_DERIVED_LINEAGE_NOT_ADMITTED"
                    )
                if input_ref not in snapshot_rows:
                    snapshot_rows[input_ref] = input_row
                    pending.append(input_row)
        facts: list[dict[str, Any]] = []
        selected_categories: set[str] = set()
        for ref, datum in sorted(snapshot_rows.items()):
            row = datum.to_document()
            selected_categories.add(str(row["category"]))
            derived = datum.epistemic_type is not DatumEpistemicType.OBSERVED_FACT
            predicate_quality = _datum_quality(datum, admitted=True)
            facts.append(
                {
                    "fact_id": ref,
                    "kind": "DERIVED_FEATURE" if derived else "RAW_FACT",
                    "category": row["category"],
                    "metric": row["metric"],
                    "value": row["value"],
                    "unit": row["unit"],
                    "symbol": row["instrument_id"],
                    "timeframe": row["timeframe"],
                    "window": row["window"],
                    "source_ref": row["source_ref"],
                    "raw_ref": row["raw_ref"],
                    "raw_sha256": row["raw_sha256"],
                    "observed_at": row["observed_at"],
                    "available_at": row["available_at"],
                    "quality": (
                        "GOOD"
                        if predicate_quality is PredicateQuality.HIGH
                        else "UNKNOWN"
                        if predicate_quality is PredicateQuality.UNKNOWN
                        else "DEGRADED"
                    ),
                    "coverage": row["coverage"],
                    "dependency_group": row["dependency_group"],
                    "lineage": list(datum.input_refs) if derived else [],
                    "transform": datum.formula_version if derived else None,
                    "limitations": "; ".join(row["limitations"]),
                    "missing_reason": None,
                }
            )
        for category in MARKET_CATEGORIES:
            if category in selected_categories:
                continue
            facts.append(
                {
                    "fact_id": f"sentiment:unknown:{category}",
                    "kind": "RAW_FACT",
                    "category": category,
                    "metric": f"unavailable-{category.lower()}",
                    "value": None,
                    "unit": "UNAVAILABLE",
                    "symbol": packet["symbol"],
                    "timeframe": "1H",
                    "window": "POINT_IN_TIME",
                    "source_ref": f"unavailable:{category}",
                    "raw_ref": f"unavailable/{category}.json",
                    "raw_sha256": None,
                    "observed_at": packet["decision_at"],
                    "available_at": packet["decision_at"],
                    "quality": "UNKNOWN",
                    "coverage": "0",
                    "dependency_group": f"UNKNOWN:{category}",
                    "lineage": [],
                    "transform": None,
                    "limitations": "No admitted direct sentiment evidence for this category.",
                    "missing_reason": "NO_AGENT_ADMITTED_DIRECT_EVIDENCE",
                }
            )
        snapshot = build_market_information_snapshot(
            run_id=packet["run_id"],
            cycle_index=packet["cycle_index"],
            symbol=packet["symbol"],
            as_of=packet["decision_at"],
            facts=facts,
        )
        dimensions: list[dict[str, Any]] = []
        for legacy_axis in SENTIMENT_AXES:
            row = analyses[_LEGACY_TO_V31[legacy_axis]]
            contributors = []
            actual_groups = []
            contributions_by_timeframe: dict[str, list[int]] = {}
            for assessment in row["evidence_assessments"]:
                datum = rows_by_id[assessment["evidence_ref"]]
                actual_groups.append(datum.dependency_group)
                contributions_by_timeframe.setdefault(
                    datum.timeframe, []
                ).append(int(assessment["ordinal_contribution"]))
                contributors.append(
                    {
                        "fact_id": assessment["evidence_ref"],
                        "ordinal_contribution": assessment[
                            "ordinal_contribution"
                        ],
                        "rule": assessment["rule"],
                        "direction": assessment["direction"],
                    }
                )
            required_groups = row["required_dependency_groups"]
            if not set(actual_groups).issubset(set(required_groups)):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_SENTIMENT_DEPENDENCY_GROUP_MISMATCH"
                )
            declared_timeframes = row["timeframe_states"]
            if not contributions_by_timeframe:
                if any(value is not None for value in declared_timeframes.values()):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_UNKNOWN_SENTIMENT_TIMEFRAME_NOT_UNKNOWN"
                    )
            else:
                if not set(contributions_by_timeframe).issubset(
                    declared_timeframes
                ):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_SENTIMENT_EVIDENCE_TIMEFRAME_MISSING"
                    )
                expected_timeframes: dict[str, int] = {}
                for timeframe, values in contributions_by_timeframe.items():
                    signs = {value > 0 for value in values if value != 0}
                    if legacy_axis == "TIMEFRAME_COHERENCE" and len(signs) != 1:
                        reduced = 0
                    else:
                        balance = sum(values)
                        reduced = max(
                            -1 if len(signs) > 1 else -2,
                            min(1 if len(signs) > 1 else 2, balance),
                        )
                    expected_timeframes[timeframe] = reduced
                if any(
                    declared_timeframes.get(timeframe) != value
                    for timeframe, value in expected_timeframes.items()
                ) or any(
                    value is not None and timeframe not in expected_timeframes
                    for timeframe, value in declared_timeframes.items()
                ):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_SENTIMENT_TIMEFRAME_REPLAY_MISMATCH"
                    )
            dimensions.append(
                {
                    "axis": legacy_axis,
                    "required_dependency_groups": required_groups,
                    "contributors": contributors,
                    "timeframe_states": row["timeframe_states"],
                    "agent_interpretation": row["reasoning"],
                    "limitations": "; ".join(row["limitations"]),
                    "next_discriminating_observation": row[
                        "next_discriminating_observation"
                    ],
                }
            )
        legacy = build_sentiment_state(
            market_snapshot=snapshot,
            dimension_inputs=dimensions,
            operational_synthesis=envelope["operational_synthesis"],
        )
        evidence_bindings = {
            ref: {
                "evidence_ref": ref,
                "evidence_digest": datum.to_document()["datum_digest"],
                "admissibility_level": "INFERENCE_ADMISSIBLE",
            }
            for ref, datum in selected.items()
        }
        state = migrate_legacy_sentiment_state_to_v31(
            legacy_sentiment_state=legacy,
            market_information_snapshot=snapshot,
            pit_dataset_digest=str(dataset["dataset_digest"]),
            sentiment_evidence_bindings=evidence_bindings,
            downstream_scope="PATH_ACTION",
            previous_v31_sentiment_state=previous_sentiment_state,
        )
        by_axis = {row["axis"]: row for row in state["dimensions"]}
        if any(
            by_axis[axis]["ordinal_value"]
            != _STATE_TO_ORDINAL[analyses[axis]["ordinal_state"]]
            for axis in _LEGACY_TO_V31.values()
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_SENTIMENT_DECLARED_STATE_REPLAY_MISMATCH"
            )
        change = build_sentiment_state_change(
            current_sentiment_state=state,
            changed_at=packet["decision_at"],
            previous_sentiment_state=previous_sentiment_state,
        )
        return snapshot, dimensions, state, change

    def _dynamic_state(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        datum_bindings: Mapping[str, str],
        previous_registry: Mapping[str, Any] | None,
        previous_ledger: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        hypothesis_deltas: list[dict[str, Any]] = []
        prior_hypotheses = {
            str(row["hypothesis_id"]): row
            for row in (
                []
                if previous_registry is None
                else previous_registry["hypotheses"]
            )
        }
        for raw in _rows(
            envelope["hypothesis_deltas"],
            "V31_SEMANTIC_HYPOTHESIS_DELTAS_INVALID",
        ):
            if set(raw) != _HYPOTHESIS_DELTA_FIELDS:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_HYPOTHESIS_DELTA_SCHEMA_INVALID"
                )
            operation = str(raw["operation"])
            if operation == "RESTORE":
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_HYPOTHESIS_ID_RESURRECTION_FORBIDDEN"
                )
            prior_decision = (
                None
                if previous_registry is None
                else _moment(
                    previous_registry["decision_at"],
                    "V31_SEMANTIC_HYPOTHESIS_PRIOR_TIME_INVALID",
                )
            )
            occurred = _moment(
                raw["occurred_at"],
                "V31_SEMANTIC_HYPOTHESIS_DELTA_TIME_INVALID",
            )
            if prior_decision is not None and occurred <= prior_decision:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_HYPOTHESIS_DELTA_TIME_NOT_MONOTONIC"
                )
            evidence_ids = _string_rows(
                raw["evidence_ids"],
                "V31_SEMANTIC_HYPOTHESIS_EVIDENCE_INVALID",
                allow_empty=operation in {"ARCHIVE", "EXPIRE"},
            )
            if not set(evidence_ids).issubset(datum_bindings):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_HYPOTHESIS_EVIDENCE_NOT_ADMITTED"
                )
            replacements = []
            for replacement in _mapping_rows(
                raw["replacement_hypotheses"],
                "V31_SEMANTIC_HYPOTHESIS_REPLACEMENT_INVALID",
                allow_empty=True,
            ):
                if set(replacement) != _HYPOTHESIS_SPEC_FIELDS:
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_HYPOTHESIS_SCHEMA_INVALID"
                    )
                active_ids = _string_rows(
                    replacement["active_evidence_ids"],
                    "V31_SEMANTIC_HYPOTHESIS_EVIDENCE_INVALID",
                )
                if not set(active_ids).issubset(datum_bindings):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_HYPOTHESIS_EVIDENCE_NOT_ADMITTED"
                    )
                prior_hypothesis = prior_hypotheses.get(
                    str(replacement["hypothesis_id"])
                )
                replacement_updated = _moment(
                    replacement["updated_at"],
                    "V31_SEMANTIC_HYPOTHESIS_UPDATE_TIME_INVALID",
                )
                if (
                    prior_hypothesis is not None
                    and replacement_updated
                    <= _moment(
                        prior_hypothesis["updated_at"],
                        "V31_SEMANTIC_HYPOTHESIS_PRIOR_UPDATE_TIME_INVALID",
                    )
                ) or (
                    prior_hypothesis is None
                    and prior_decision is not None
                    and _moment(
                        replacement["created_at"],
                        "V31_SEMANTIC_HYPOTHESIS_CREATE_TIME_INVALID",
                    )
                    <= prior_decision
                ):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_HYPOTHESIS_TIME_NOT_MONOTONIC"
                    )
                replacements.append(
                    {
                        **dict(replacement),
                        "active_evidence_ids": list(active_ids),
                        "active_evidence_bindings": {
                            ref: datum_bindings[ref] for ref in sorted(active_ids)
                        },
                    }
                )
            hypothesis_deltas.append(
                {
                    **dict(raw),
                    "replacement_hypotheses": replacements,
                    "evidence_ids": list(evidence_ids),
                    "evidence_bindings": {
                        ref: datum_bindings[ref] for ref in sorted(evidence_ids)
                    },
                }
            )
        registry = reduce_hypothesis_registry(
            previous_registry=previous_registry,
            deltas=hypothesis_deltas,
            decision_at=packet["decision_at"],
        )

        expectation_deltas: list[dict[str, Any]] = []
        prior_expectations = {
            str(row["expectation_id"]): row
            for row in (
                []
                if previous_ledger is None
                else previous_ledger["expectations"]
            )
        }
        for raw in _rows(
            envelope["expectation_deltas"],
            "V31_SEMANTIC_EXPECTATION_DELTAS_INVALID",
        ):
            if set(raw) != _EXPECTATION_DELTA_FIELDS:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_EXPECTATION_DELTA_SCHEMA_INVALID"
                )
            if previous_ledger is not None and _moment(
                raw["occurred_at"],
                "V31_SEMANTIC_EXPECTATION_DELTA_TIME_INVALID",
            ) <= _moment(
                previous_ledger["decision_at"],
                "V31_SEMANTIC_EXPECTATION_PRIOR_TIME_INVALID",
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_EXPECTATION_DELTA_TIME_NOT_MONOTONIC"
                )
            expectation = raw["expectation"]
            if not isinstance(expectation, Mapping) or set(expectation) != _EXPECTATION_SPEC_FIELDS:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_EXPECTATION_SCHEMA_INVALID"
                )
            result_refs = _string_rows(
                expectation["result_evidence_refs"],
                "V31_SEMANTIC_EXPECTATION_RESULT_EVIDENCE_INVALID",
                allow_empty=True,
            )
            if not set(result_refs).issubset(datum_bindings):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_EXPECTATION_RESULT_EVIDENCE_NOT_ADMITTED"
                )
            prior_expectation = prior_expectations.get(
                str(expectation["expectation_id"])
            )
            prior_ledger_decision = (
                None
                if previous_ledger is None
                else _moment(
                    previous_ledger["decision_at"],
                    "V31_SEMANTIC_EXPECTATION_PRIOR_TIME_INVALID",
                )
            )
            if (
                prior_expectation is not None
                and _moment(
                    expectation["updated_at"],
                    "V31_SEMANTIC_EXPECTATION_UPDATE_TIME_INVALID",
                )
                <= _moment(
                    prior_expectation["updated_at"],
                    "V31_SEMANTIC_EXPECTATION_PRIOR_UPDATE_TIME_INVALID",
                )
            ) or (
                prior_expectation is None
                and prior_ledger_decision is not None
                and _moment(
                    expectation["created_at"],
                    "V31_SEMANTIC_EXPECTATION_CREATE_TIME_INVALID",
                )
                <= prior_ledger_decision
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_EXPECTATION_TIME_NOT_MONOTONIC"
                )
            expectation_deltas.append(
                {
                    **dict(raw),
                    "expectation": {
                        **dict(expectation),
                        "result_evidence_refs": list(result_refs),
                        "result_evidence_bindings": {
                            ref: datum_bindings[ref] for ref in sorted(result_refs)
                        },
                    },
                }
            )
        ledger = reduce_expectation_ledger(
            previous_ledger=previous_ledger,
            deltas=expectation_deltas,
            decision_at=packet["decision_at"],
            valid_hypothesis_ids=registry["known_hypothesis_ids"],
        )
        return registry, hypothesis_deltas, ledger, expectation_deltas

    def _cloud(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        rows_by_id: Mapping[str, PointInTimeDatum],
        registry: Mapping[str, Any],
        previous_cloud: ProbabilityCloud | None,
    ) -> ProbabilityCloud:
        spec = envelope["probability_cloud_spec"]
        active = set(registry["active_hypothesis_ids"])
        components = []
        for raw in spec["components"]:
            hypothesis_id = raw["hypothesis_id"]
            if hypothesis_id not in active | {"OTHER", "UNKNOWN"}:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CLOUD_HYPOTHESIS_NOT_ACTIVE"
                )
            refs = set(raw["evidence_refs"]) | set(raw["opposition_refs"]) | set(
                raw["conflict_refs"]
            )
            if not refs.issubset(rows_by_id):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CLOUD_EVIDENCE_NOT_ADMITTED"
                )
            if any(
                rows_by_id[ref].to_document()["inference_admissible"] is not True
                or rows_by_id[ref].to_document()["hypothesis_admissible"]
                is not True
                or rows_by_id[ref].value is None
                for ref in refs
            ):
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CLOUD_DIRECTIONAL_EVIDENCE_NOT_ADMISSIBLE"
                )
            groups = sorted({rows_by_id[ref].dependency_group for ref in refs})
            if raw["dependency_groups"] != groups:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CLOUD_DEPENDENCY_GROUP_MISMATCH"
                )
            components.append(
                CloudComponent(
                    hypothesis_id=hypothesis_id,
                    plausibility=PlausibilityLevel(raw["plausibility"]),
                    lower=None,
                    upper=None,
                    probability=None,
                    evidence_refs=tuple(raw["evidence_refs"]),
                    opposition_refs=tuple(raw["opposition_refs"]),
                    conflict_refs=tuple(raw["conflict_refs"]),
                    dependency_groups=tuple(raw["dependency_groups"]),
                    data_uncertainty=tuple(raw["data_uncertainty"]),
                    model_uncertainty=tuple(raw["model_uncertainty"]),
                    sensitivity_notes=tuple(raw["sensitivity_notes"]),
                )
            )
        represented = {row.hypothesis_id for row in components}
        if not active.issubset(represented):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_CLOUD_ACTIVE_HYPOTHESES_INCOMPLETE"
            )
        available = max(
            (row.available_at for row in rows_by_id.values()),
            default=_moment(packet["decision_at"], "V31_SEMANTIC_DECISION_TIME_INVALID"),
        )
        component_ids = {row.hypothesis_id for row in components}
        previous_ids = (
            None
            if previous_cloud is None
            else {row.hypothesis_id for row in previous_cloud.components}
        )
        return ProbabilityCloud(
            cloud_id=(
                previous_cloud.cloud_id
                if previous_cloud is not None and component_ids == previous_ids
                else f"cloud:{packet['run_id']}:{packet['cycle_index']:04d}"
            ),
            mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
            decision_at=packet["decision_at"],
            available_at=_time(available),
            horizon=spec["horizon"],
            components=tuple(components),
            unknown_refs=tuple(spec["unknown_refs"]),
            limitations=tuple(spec["limitations"]),
        )

    def _cloud_transition(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        rows_by_id: Mapping[str, PointInTimeDatum],
        previous_cloud: ProbabilityCloud | None,
        cloud: ProbabilityCloud,
    ) -> dict[str, Any] | None:
        if previous_cloud is None:
            return None
        roles: dict[str, set[EvidenceEffect]] = {}
        for component in cloud.components:
            for ref in component.evidence_refs:
                roles.setdefault(ref, set()).add(EvidenceEffect.SUPPORT)
            for ref in component.opposition_refs:
                roles.setdefault(ref, set()).add(EvidenceEffect.OPPOSE)
            for ref in component.conflict_refs:
                roles.setdefault(ref, set()).add(EvidenceEffect.CONFLICT)
        if not roles:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_CLOUD_TRANSITION_EVIDENCE_REQUIRED"
            )
        evidence: list[CloudUpdateEvidence] = []
        conflict_refs: list[str] = []
        for ref, effects in sorted(roles.items()):
            datum = rows_by_id.get(ref)
            if datum is None:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_CLOUD_TRANSITION_EVIDENCE_NOT_CURRENT"
                )
            quality = _datum_quality(
                datum,
                admitted=datum.to_document()["inference_admissible"] is True,
            )
            effect = (
                EvidenceEffect.CONFLICT
                if EvidenceEffect.CONFLICT in effects or len(effects) > 1
                else next(iter(effects))
            )
            if effect is EvidenceEffect.CONFLICT:
                conflict_refs.append(ref)
            evidence.append(
                CloudUpdateEvidence(
                    evidence_ref=ref,
                    evidence_digest=datum.to_document()["datum_digest"],
                    available_at=_time(datum.available_at),
                    quality=quality.value,
                    effect=effect,
                    dependency_group=datum.dependency_group,
                    regime_ref=datum.regime_ref or "regime:unclassified",
                    limitations=tuple(datum.limitations),
                )
            )
        sensitivities = tuple(
            dict.fromkeys(
                [
                    *envelope["probability_cloud_spec"]["limitations"],
                    *(
                        note
                        for component in cloud.components
                        for note in component.sensitivity_notes
                    ),
                ]
            )
        )
        prior_ids = {row.hypothesis_id for row in previous_cloud.components}
        current_ids = {row.hypothesis_id for row in cloud.components}
        try:
            if prior_ids == current_ids:
                return seal_probability_cloud_update(
                    prior_cloud=previous_cloud,
                    updated_cloud=cloud,
                    evidence=tuple(evidence),
                    dependency_adjustments=tuple(
                        sorted({row.dependency_group for row in evidence})
                    ),
                    conflict_refs=tuple(conflict_refs),
                    update_method=(
                        "AGENT_AUTHORED_ORDINAL_COMPONENT_REPLAY"
                    ),
                    model_version=self.compiler_id,
                    sensitivity_notes=sensitivities,
                    updated_at=packet["decision_at"],
                )
            return seal_probability_cloud_repartition(
                prior_cloud=previous_cloud,
                repartitioned_cloud=cloud,
                evidence=tuple(evidence),
                added_hypothesis_reasons={
                    hypothesis_id: (
                        "Agent-authored component added after explicit "
                        "hypothesis lifecycle transition."
                    )
                    for hypothesis_id in sorted(current_ids - prior_ids)
                },
                retired_hypothesis_reasons={
                    hypothesis_id: (
                        "Component retired after explicit hypothesis "
                        "lifecycle transition; history remains retained."
                    )
                    for hypothesis_id in sorted(prior_ids - current_ids)
                },
                sensitivity_notes=sensitivities,
                repartitioned_at=packet["decision_at"],
            )
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_CLOUD_TRANSITION_INVALID"
            ) from exc

    def _paths(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        rows_by_id: Mapping[str, PointInTimeDatum],
        ledger: Mapping[str, Any],
    ) -> ScenarioPathSet:
        expectations = {
            row["expectation_id"]: row for row in ledger["expectations"]
        }

        def predicate(raw: Mapping[str, Any]) -> PathPredicate:
            timing = PredicateTiming(raw["timing"])
            datum = rows_by_id.get(raw["fact_ref"])
            if timing is PredicateTiming.DECISION_INPUT:
                if datum is None or raw["available_at"] != _time(datum.available_at):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_PATH_INPUT_NOT_ADMITTED"
                    )
                digest = datum.to_document()["datum_digest"]
            else:
                digest = None
            return PathPredicate(
                predicate_id=raw["predicate_id"],
                fact_ref=raw["fact_ref"],
                fact_digest=digest,
                timing=timing,
                operator=PredicateOperator(raw["operator"]),
                expected=raw["expected"],
                available_at=raw["available_at"],
                minimum_quality=PredicateQuality(raw["minimum_quality"]),
                minimum_coverage=raw["minimum_coverage"],
                allowed_conflict_states=tuple(raw["allowed_conflict_states"]),
                limitations=tuple(raw["limitations"]),
            )

        spec = envelope["scenario_path_set_spec"]
        paths = []
        for raw in spec["paths"]:
            path_expectations = []
            for expected in raw["expectations"]:
                row = expectations.get(expected["observation_id"])
                if row is None or row["hypothesis_id"] != expected["hypothesis_id"]:
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_PATH_EXPECTATION_NOT_REGISTERED"
                    )
                path_expectations.append(
                    ExpectedObservation(
                        observation_id=expected["observation_id"],
                        hypothesis_id=expected["hypothesis_id"],
                        expectation_revision_digest=canonical_digest(row),
                        observable_ref=expected["observable_ref"],
                        horizon_at=expected["horizon_at"],
                        direction_or_state=expected["direction_or_state"],
                        confirms_when=expected["confirms_when"],
                        contradicts_when=expected["contradicts_when"],
                    )
                )
            paths.append(
                ScenarioPathRule(
                    path_id=raw["path_id"],
                    decision_at=packet["decision_at"],
                    triggers=tuple(predicate(row) for row in raw["triggers"]),
                    guards=tuple(predicate(row) for row in raw["guards"]),
                    unless=tuple(predicate(row) for row in raw["unless"]),
                    transition=EpistemicTransition(
                        from_stage=EpistemicStage(raw["transition"]["from_stage"]),
                        to_stage=EpistemicStage(raw["transition"]["to_stage"]),
                        target_ref=raw["transition"]["target_ref"],
                        update_type=raw["transition"]["update_type"],
                    ),
                    mechanism=raw["mechanism"],
                    mechanism_hypothesis_refs=tuple(
                        raw["mechanism_hypothesis_refs"]
                    ),
                    expectations=tuple(path_expectations),
                    falsifiers=tuple(predicate(row) for row in raw["falsifiers"]),
                    else_path_refs=tuple(raw["else_path_refs"]),
                    preserves_other_unknown=raw["preserves_other_unknown"],
                    action_implications=tuple(
                        ActionImplication(
                            action=ActionType(row["action"]),
                            effect=ImplicationEffect(row["effect"]),
                            rationale=row["rationale"],
                            risk_refs=tuple(row["risk_refs"]),
                            opportunity_cost=row["opportunity_cost"],
                        )
                        for row in raw["action_implications"]
                    ),
                    expires_at=raw["expires_at"],
                    next_review_at=raw["next_review_at"],
                    next_observation=raw["next_observation"],
                    regime_refs=tuple(raw["regime_refs"]),
                    probability_cloud_refs=tuple(raw["probability_cloud_refs"]),
                )
            )
        return ScenarioPathSet(
            set_id=spec["set_id"],
            decision_at=packet["decision_at"],
            paths=tuple(paths),
            lead_path_id=spec["lead_path_id"],
            runner_up_path_id=spec["runner_up_path_id"],
            residual_path_id=spec["residual_path_id"],
        )

    def _actions(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        experiment: Mapping[str, Any],
        rows_by_id: Mapping[str, PointInTimeDatum],
        cloud: ProbabilityCloud,
    ) -> tuple[PortfolioDecisionContext, dict[str, Any]]:
        shadow = experiment.get("portfolio_scope", {}).get("financial_shadow")
        if not isinstance(shadow, Mapping):
            raise V31SemanticCompilerError("V31_SEMANTIC_FINANCIAL_SHADOW_MISSING")
        account = shadow.get("initial_shadow_account")
        grid = shadow.get("candidate_grid")
        economics = shadow.get("market_economics_policy")
        risk_input = shadow.get("risk_policy")
        if not all(isinstance(row, Mapping) for row in (account, grid, economics, risk_input)):
            raise V31SemanticCompilerError("V31_SEMANTIC_FINANCIAL_SHADOW_INVALID")
        marks = [
            row
            for row in rows_by_id.values()
            if row.metric == "mark-price"
            and row.instrument_id == packet["symbol"]
            and row.to_document()["inference_admissible"] is True
        ]
        if len(marks) != 1:
            raise V31SemanticCompilerError("V31_SEMANTIC_MARK_PRICE_NOT_UNIQUE")
        mark_row = marks[0]
        mark = Decimal(str(mark_row.value))
        tick = Decimal(str(economics["price_tick_usdt"]))
        long_unrounded = mark * Decimal(
            str(economics["long_protective_stop_multiplier"])
        )
        short_unrounded = mark * Decimal(
            str(economics["short_protective_stop_multiplier"])
        )
        long_stop = (long_unrounded / tick).to_integral_value(
            rounding=ROUND_FLOOR
        ) * tick
        short_stop = (short_unrounded / tick).to_integral_value(
            rounding=ROUND_CEILING
        ) * tick
        position_input = {
            "intended_side": account["target_position"],
            "mark_price": str(mark),
            "contract_multiplier": economics["contract_multiplier"],
            "reentry_contract_active": False,
            "account": {
                "equity_usdt": account["equity_usdt"],
                "margin_used_usdt": account["margin_used_usdt"],
                "margin_available_usdt": account["margin_available_usdt"],
                "max_gross_leverage": account["max_gross_leverage"],
            },
            "lots": list(account["other_lots"]),
            "pending_orders": list(account["pending_orders"]),
        }
        position = build_lot_position_truth(
            symbol=packet["symbol"], position_truth=position_input
        )
        risk = build_financial_risk_policy(risk_input)
        context = PortfolioDecisionContext(
            decision_at=packet["decision_at"],
            position_side=PositionSide(grid["position_side"]),
            lot_ids=(),
            pending_reentry_side=None,
            portfolio_truth_digest=position["position_truth_digest"],
            risk_policy_digest=risk["risk_policy_digest"],
            probability_mode=ProbabilityMode.SUBJECTIVE_PLAUSIBILITY,
            probability_cloud_digest=cloud.to_document()["cloud_digest"],
            entry_scale_grid_pct=tuple(grid["entry_scale_grid_pct"]),
            partial_exit_scale_grid_pct=tuple(grid["partial_exit_scale_grid_pct"]),
            allowed_entry_roles=tuple(
                PositionRole(value) for value in grid["allowed_entry_roles"]
            ),
        )
        legal = legal_action_keys(context)
        specs = {
            (row["action"], row["scale_pct"], row["target_role"]): row
            for row in envelope["action_candidate_specs"]
        }
        legal_keys = {
            (
                key.action.value,
                key.scale_pct,
                None if key.target_role is None else key.target_role.value,
            )
            for key in legal
        }
        if set(specs) != legal_keys or len(specs) != len(legal):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_ACTION_GRID_NOT_EXACTLY_FROZEN"
            )
        candidates = []
        for key in legal:
            spec = specs[
                (
                    key.action.value,
                    key.scale_pct,
                    None if key.target_role is None else key.target_role.value,
                )
            ]
            candidates.append(
                ActionCandidate(
                    candidate_id=spec["candidate_id"],
                    action=key.action,
                    target_lot_ids=key.target_lot_ids,
                    scale_pct=key.scale_pct,
                    target_role=key.target_role,
                    trigger_conditions=tuple(spec["trigger_conditions"]),
                    invalidation_conditions=tuple(spec["invalidation_conditions"]),
                    path_refs=tuple(spec["path_refs"]),
                    evidence_refs=tuple(spec["evidence_refs"]),
                    risk_refs=tuple(spec["risk_refs"]),
                    thesis=spec["thesis"],
                    wait_reason=spec["wait_reason"],
                    opportunity_cost=spec["opportunity_cost"],
                    next_observation=spec["next_observation"],
                    next_review_at=spec["next_review_at"],
                    information_not_arrived_default=spec[
                        "information_not_arrived_default"
                    ],
                    position_protection_responsibility=spec[
                        "position_protection_responsibility"
                    ],
                )
            )
        financial = build_financial_evaluation_receipt(
            run_id=packet["run_id"],
            cycle_index=packet["cycle_index"],
            decision_at=packet["decision_at"],
            evaluated_at=packet["decision_at"],
            symbol=packet["symbol"],
            position_truth=position_input,
            risk_policy=risk_input,
            market_economics={
                "symbol": packet["symbol"],
                "available_at": _time(mark_row.available_at),
                "mark_price": str(mark),
                "contract_multiplier": economics["contract_multiplier"],
                "contract_size_multiplier": economics[
                    "contract_size_multiplier"
                ],
                "quantity_step_contracts": economics[
                    "quantity_step_contracts"
                ],
                "minimum_quantity_contracts": economics[
                    "minimum_quantity_contracts"
                ],
                "price_tick_usdt": economics["price_tick_usdt"],
                "long_protective_stop_price": str(long_stop),
                "short_protective_stop_price": str(short_stop),
            },
            probability_mode=context.probability_mode,
            probability_cloud_digest=context.probability_cloud_digest,
            calibration_receipt_digests=(),
            proper_scoring_receipt_digests=(),
            oos_evaluation_receipt_digests=(),
            candidates=tuple(row.to_document() for row in candidates),
        )
        evaluations = action_evaluations_from_financial_receipt(
            financial_evaluation_receipt=financial,
            candidates=tuple(candidates),
        )
        evaluation = seal_complete_action_evaluation(
            run_id=packet["run_id"],
            cycle_index=packet["cycle_index"],
            context=context,
            candidates=tuple(candidates),
            evaluations=evaluations,
            financial_evaluation_receipt=financial,
            evaluated_at=packet["decision_at"],
        )
        return context, evaluation

    def _graph(
        self,
        *,
        packet: Mapping[str, Any],
        envelope: Mapping[str, Any],
        admissions: Sequence[AdmittedInformationEvent],
        rows_by_id: Mapping[str, PointInTimeDatum],
        all_rows_by_id: Mapping[str, PointInTimeDatum],
        cloud: ProbabilityCloud,
        registry: Mapping[str, Any],
        ledger: Mapping[str, Any],
        paths: ScenarioPathSet,
        action_evaluation: Mapping[str, Any],
        prior_graph: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        spec = envelope["graph_delta_spec"]
        if spec["projection_id"] != self.compiler_id:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_GRAPH_COMPILER_PROJECTION_ID_MISMATCH"
            )
        decision = _moment(packet["decision_at"], "V31_SEMANTIC_DECISION_TIME_INVALID")
        created = decision - timedelta(microseconds=1)
        prior = (
            create_market_knowledge_graph(
                graph_id=spec["graph_id"], created_at=_time(created)
            )
            if prior_graph is None
            else dict(prior_graph)
        )
        try:
            verify_market_knowledge_graph(prior, decision_at=packet["decision_at"])
        except ValueError as exc:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_PRIOR_GRAPH_INVALID"
            ) from exc
        if prior.get("graph_id") != spec["graph_id"]:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_GRAPH_IDENTITY_MISMATCH"
            )
        prior_nodes: dict[str, dict[str, Any]] = {}
        for row in prior["node_history"]:
            prior_nodes[str(row["node_id"])] = dict(row)
        prior_associations: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in prior["association_history"]:
            key = (
                str(row["source_node_id"]),
                str(row["target_node_id"]),
                str(row["relation"]),
            )
            if row["status"] != "ACTIVE":
                if prior_associations.get(key, {}).get("association_id") == row[
                    "association_id"
                ]:
                    prior_associations.pop(key, None)
                continue
            if key in prior_associations and prior_associations[key][
                "association_id"
            ] != row["association_id"]:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_PRIOR_GRAPH_ASSOCIATION_AMBIGUOUS"
                )
            prior_associations[key] = dict(row)
        cloud_document = cloud.to_document()
        hypotheses = {
            row["hypothesis_id"]: row for row in registry["hypotheses"]
        }
        expectations = {
            row["expectation_id"]: row for row in ledger["expectations"]
        }
        path_documents = {row["path_id"]: row for row in paths.to_document()["paths"]}
        evaluation_by_id = {
            row["candidate_id"]: row for row in action_evaluation["evaluations"]
        }
        candidate_documents = {
            row["candidate_id"]: row for row in action_evaluation["candidates"]
        }
        candidate_bindings = {
            candidate_id: canonical_digest(
                {
                    "candidate": row,
                    "evaluation": evaluation_by_id[candidate_id],
                }
            )
            for candidate_id, row in candidate_documents.items()
        }
        payloads: list[tuple[str, str, str, str, tuple[str, ...]]] = []
        node_status_by_id: dict[str, str] = {}
        event_node_by_id = {
            str(row["payload_ref"]): str(row["node_id"])
            for row in prior_nodes.values()
            if row["node_type"] == "INFORMATION_EVENT"
        }
        for admission in admissions:
            event_id = admission.event.event_id
            node_id = f"node:information:{canonical_digest(event_id)[:16]}"
            event_node_by_id[event_id] = node_id
            payloads.append(
                (
                    node_id,
                    "INFORMATION_EVENT",
                    event_id,
                    admission.information_event_digest,
                    ("INFORMATION_EVENT",),
                )
            )
        datum_node_by_id = {
            str(row["payload_ref"]): str(row["node_id"])
            for row in prior_nodes.values()
            if row["node_type"] in {"MARKET_FACT", "DERIVED_MEASURE"}
        }
        for datum_id, datum in sorted(rows_by_id.items()):
            document = datum.to_document()
            node_type = (
                "MARKET_FACT"
                if datum.epistemic_type is DatumEpistemicType.OBSERVED_FACT
                else "DERIVED_MEASURE"
            )
            node_id = f"node:datum:{canonical_digest(datum_id)[:16]}"
            datum_node_by_id[datum_id] = node_id
            payloads.append(
                (
                    node_id,
                    node_type,
                    datum_id,
                    document["datum_digest"],
                    (datum.dependency_group,),
                )
            )
        cloud_node = f"node:cloud:{canonical_digest(cloud.cloud_id)[:16]}"
        payloads.append(
            (
                cloud_node,
                "LATENT_STATE",
                cloud.cloud_id,
                cloud_document["cloud_digest"],
                tuple(
                    sorted(
                        {
                            group
                            for component in cloud.components
                            for group in component.dependency_groups
                        }
                        or {"ORDINAL_CLOUD"}
                    )
                ),
            )
        )
        node_status_by_id[cloud_node] = "ACTIVE"
        hypothesis_node_by_id = {}
        for hypothesis_id, document in sorted(hypotheses.items()):
            node_id = f"node:hypothesis:{canonical_digest(hypothesis_id)[:16]}"
            hypothesis_node_by_id[hypothesis_id] = node_id
            groups = tuple(
                sorted(
                    {
                        all_rows_by_id[ref].dependency_group
                        for ref in document["active_evidence_ids"]
                    }
                )
            )
            payloads.append(
                (
                    node_id,
                    (
                        "MECHANISM_HYPOTHESIS"
                        if document["hypothesis_type"] == "MECHANISM"
                        else "PATH_HYPOTHESIS"
                    ),
                    hypothesis_id,
                    canonical_digest(document),
                    groups or ("HYPOTHESIS_SEMANTICS",),
                )
            )
            node_status_by_id[node_id] = (
                "SUPERSEDED"
                if document["state"] == "SUPERSEDED"
                else "RETIRED"
                if document["state"]
                in {"INVALIDATED", "EXPIRED", "ARCHIVED"}
                else "ACTIVE"
            )
        expectation_node_by_id = {}
        for expectation_id, document in sorted(expectations.items()):
            node_id = f"node:expectation:{canonical_digest(expectation_id)[:16]}"
            expectation_node_by_id[expectation_id] = node_id
            payloads.append(
                (
                    node_id,
                    "EXPECTATION",
                    expectation_id,
                    canonical_digest(document),
                    ("EXPECTATION_SEMANTICS",),
                )
            )
            node_status_by_id[node_id] = (
                "RETIRED"
                if document["status"]
                in {"FULFILLED", "FALSIFIED", "EXPIRED", "CANCELLED"}
                else "ACTIVE"
            )
        path_node_by_id = {}
        for path_id, document in sorted(path_documents.items()):
            node_id = f"node:path:{canonical_digest(path_id)[:16]}"
            path_node_by_id[path_id] = node_id
            payloads.append(
                (
                    node_id,
                    "SCENARIO_PATH",
                    path_id,
                    document["path_digest"],
                    ("SCENARIO_PATH",),
                )
            )
        action_node_by_id = {}
        for candidate_id, digest in sorted(candidate_bindings.items()):
            node_id = f"node:action:{canonical_digest(candidate_id)[:16]}"
            action_node_by_id[candidate_id] = node_id
            payloads.append(
                (
                    node_id,
                    "ACTION_CANDIDATE",
                    candidate_id,
                    digest,
                    ("ACTION_CANDIDATE",),
                )
            )

        current_payload_node_ids = {row[0] for row in payloads}
        nodes = []
        for node_id, node_type, payload_ref, payload_digest, groups in payloads:
            previous_node = prior_nodes.get(node_id)
            if previous_node is not None and previous_node["node_type"] != node_type:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_GRAPH_NODE_TYPE_MUTATION_FORBIDDEN"
                )
            desired_status = node_status_by_id.get(node_id, "ACTIVE")
            if previous_node is not None and previous_node["status"] in {
                "SUPERSEDED",
                "RETIRED",
            }:
                if (
                    desired_status == "ACTIVE"
                    or previous_node["payload_digest"] != payload_digest
                ):
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_GRAPH_TERMINAL_NODE_RESURRECTION_FORBIDDEN"
                    )
                continue
            if previous_node is not None and (
                previous_node["payload_ref"] == payload_ref
                and previous_node["payload_digest"] == payload_digest
                and previous_node["status"] == desired_status
                and previous_node["dependency_group_ids"] == list(groups)
            ):
                continue
            nodes.append(
                build_graph_node_revision(
                    {
                        "schema_version": "V3_1_GRAPH_NODE_REVISION",
                        "node_id": node_id,
                        "revision": (
                            1
                            if previous_node is None
                            else int(previous_node["revision"]) + 1
                        ),
                        "predecessor_digest": (
                            None
                            if previous_node is None
                            else previous_node["node_digest"]
                        ),
                        "node_type": node_type,
                        "label": payload_ref,
                        "description": "Exact typed artifact projection; no additional market claim.",
                        "payload_ref": payload_ref,
                        "payload_digest": payload_digest,
                        "observed_at": packet["decision_at"],
                        "available_at": packet["decision_at"],
                        "validity": {
                            "valid_from": packet["decision_at"],
                            "valid_until": None,
                        },
                        "status": desired_status,
                        "dependency_group_ids": list(groups),
                        "provenance": [
                            {
                                "source_ref": payload_ref,
                                "source_digest": payload_digest,
                                "observed_at": packet["decision_at"],
                                "available_at": packet["decision_at"],
                                "revision_ref": f"{payload_ref}@cycle-{packet['cycle_index']}",
                            }
                        ],
                        "created_at": (
                            packet["decision_at"]
                            if previous_node is None
                            else previous_node["created_at"]
                        ),
                        "limitations": [
                            "Projection records bindings and Agent-authored semantics; it is not causal proof."
                        ],
                    },
                    decision_at=packet["decision_at"],
                    prior_revision=previous_node,
                )
            )

        # A repartition or an Agent-authored path/candidate identity change
        # leaves history intact but cannot leave the replaced analytical head
        # active in the current graph.
        for previous_node in prior_nodes.values():
            if (
                previous_node["node_type"]
                in {"LATENT_STATE", "SCENARIO_PATH", "ACTION_CANDIDATE"}
                and previous_node["node_id"] not in current_payload_node_ids
                and previous_node["status"] == "ACTIVE"
            ):
                nodes.append(
                    build_graph_node_revision(
                        {
                            **{
                                key: value
                                for key, value in previous_node.items()
                                if key != "node_digest"
                            },
                            "revision": int(previous_node["revision"]) + 1,
                            "predecessor_digest": previous_node["node_digest"],
                            "observed_at": packet["decision_at"],
                            "available_at": packet["decision_at"],
                            "validity": {
                                "valid_from": previous_node["validity"][
                                    "valid_from"
                                ],
                                "valid_until": packet["decision_at"],
                            },
                            "status": "RETIRED",
                            "provenance": [
                                *previous_node["provenance"],
                                {
                                    "source_ref": spec["projection_id"],
                                    "source_digest": envelope[
                                        "agent_authoring_envelope_digest"
                                    ],
                                    "observed_at": packet["decision_at"],
                                    "available_at": packet["decision_at"],
                                    "revision_ref": spec["delta_id"],
                                },
                            ],
                        },
                        decision_at=packet["decision_at"],
                        prior_revision=previous_node,
                    )
                )

        edge_specs: list[tuple[str, str, str]] = []
        for datum_id, datum in sorted(rows_by_id.items()):
            if datum.epistemic_type is DatumEpistemicType.OBSERVED_FACT:
                for event_id in datum.event_ids:
                    if event_id not in event_node_by_id:
                        raise V31SemanticCompilerError(
                            "V31_SEMANTIC_GRAPH_DATUM_EVENT_NOT_ADMITTED"
                        )
                    edge_specs.append(
                        (event_node_by_id[event_id], datum_node_by_id[datum_id], "DESCRIBES")
                    )
            else:
                for input_ref in datum.input_refs:
                    if input_ref not in datum_node_by_id:
                        raise V31SemanticCompilerError(
                            "V31_SEMANTIC_GRAPH_DERIVED_INPUT_NOT_ADMITTED"
                        )
                    edge_specs.append(
                        (
                            datum_node_by_id[datum_id],
                            datum_node_by_id[input_ref],
                            "DERIVED_FROM",
                        )
                    )
        cloud_evidence_refs = {
            ref
            for component in cloud.components
            for ref in (
                *component.evidence_refs,
                *component.opposition_refs,
                *component.conflict_refs,
            )
        }
        for datum_id in sorted(cloud_evidence_refs):
            if datum_id not in datum_node_by_id:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_GRAPH_CLOUD_DATUM_NOT_ADMITTED"
                )
            edge_specs.append(
                (cloud_node, datum_node_by_id[datum_id], "CONDITIONED_BY")
            )
        represented = {row.hypothesis_id for row in cloud.components}
        for hypothesis_id in sorted(registry["active_hypothesis_ids"]):
            if hypothesis_id not in represented:
                raise V31SemanticCompilerError(
                    "V31_SEMANTIC_GRAPH_CLOUD_HYPOTHESIS_LINK_NOT_AUTHORED"
                )
            edge_specs.append(
                (cloud_node, hypothesis_node_by_id[hypothesis_id], "EVALUATES")
            )
        for expectation_id, expectation in sorted(expectations.items()):
            if expectation_id not in ledger["open_expectation_ids"]:
                continue
            edge_specs.append(
                (
                    hypothesis_node_by_id[expectation["hypothesis_id"]],
                    expectation_node_by_id[expectation_id],
                    "PRODUCES",
                )
            )
        for path_id, document in sorted(path_documents.items()):
            for expected in document["expect_by_horizon"]:
                edge_specs.append(
                    (
                        expectation_node_by_id[expected["observation_id"]],
                        path_node_by_id[path_id],
                        "INSTANTIATES",
                    )
                )

        snapshots = {
            datum_id: PathFactSnapshot(
                fact_ref=datum_id,
                fact_digest=datum.to_document()["datum_digest"],
                value=datum.value,
                available_at=_time(datum.available_at),
                missingness=datum.missingness.value,
                quality=_datum_quality(
                    datum, admitted=datum.to_document()["inference_admissible"] is True
                ),
                coverage=datum.coverage if datum.coverage is not None else "0",
                conflict_state=datum.conflict_state.value,
            )
            for datum_id, datum in rows_by_id.items()
        }
        truths = {
            rule.path_id: evaluate_path_conditions(
                rule, snapshots, evaluated_at=packet["decision_at"]
            )
            for rule in paths.paths
        }
        financially_feasible = {
            row["candidate_id"]: row["feasible"]
            for row in action_evaluation["evaluations"]
        }
        positive_edges = 0
        for candidate_id, candidate in sorted(candidate_documents.items()):
            action = ActionType(candidate["action"])
            for path_ref in candidate["path_refs"]:
                rule = next(row for row in paths.paths if row.path_id == path_ref)
                implications = [row for row in rule.action_implications if row.action is action]
                if len(implications) != 1:
                    raise V31SemanticCompilerError(
                        "V31_SEMANTIC_PATH_ACTION_IMPLICATION_NOT_EXACT"
                    )
                implication = implications[0]
                truth = truths[path_ref]
                supports = (
                    truth is PredicateTruth.TRUE
                    and implication.effect in {ImplicationEffect.FAVORS, ImplicationEffect.CONDITIONAL}
                ) or (
                    truth is PredicateTruth.UNKNOWN
                    and action is ActionType.WAIT
                    and implication.effect in {ImplicationEffect.FAVORS, ImplicationEffect.CONDITIONAL}
                )
                if supports and financially_feasible[candidate_id]:
                    edge_specs.append(
                        (path_node_by_id[path_ref], action_node_by_id[candidate_id], "SUPPORTS")
                    )
                    positive_edges += 1
                elif implication.effect is ImplicationEffect.OPPOSES:
                    edge_specs.append(
                        (path_node_by_id[path_ref], action_node_by_id[candidate_id], "OPPOSES")
                    )
        if positive_edges == 0:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_NO_SELECTABLE_PATH_ACTION_EDGE"
            )

        unique_edge_specs = sorted(set(edge_specs))
        desired_edge_keys = set(unique_edge_specs)
        terminal_node_ids = {
            node_id
            for node_id, status in node_status_by_id.items()
            if status in {"SUPERSEDED", "RETIRED"}
        } | {
            str(row["node_id"])
            for row in prior_nodes.values()
            if row["node_type"]
            in {"LATENT_STATE", "SCENARIO_PATH", "ACTION_CANDIDATE"}
            and row["node_id"] not in current_payload_node_ids
        }
        known_association_ids = {
            str(row["association_id"])
            for row in prior["association_history"]
        }
        associations = []
        for source, target, relation in unique_edge_specs:
            previous_association = prior_associations.get(
                (source, target, relation)
            )
            if previous_association is not None:
                # The structural claim and endpoints are unchanged.  Node
                # revisions carry any payload update; do not fabricate an
                # association revision merely because a new cycle ran.
                continue
            base_association_id = (
                "association:projection:"
                f"{canonical_digest({'source': source, 'target': target, 'relation': relation})[:24]}"
            )
            association_id = (
                base_association_id
                if base_association_id not in known_association_ids
                else f"{base_association_id}:cycle-{packet['cycle_index']:04d}"
            )
            associations.append(
                build_association_revision(
                    {
                        "schema_version": "V3_1_ASSOCIATION_REVISION",
                        "association_id": association_id,
                        "revision": 1,
                        "predecessor_digest": None,
                        "source_node_id": source,
                        "target_node_id": target,
                        "relation": relation,
                        "association_type": "MECHANISM_HYPOTHESIS",
                        "method": "DETERMINISTIC_EXACT_TYPED_ARTIFACT_PROJECTION_V1",
                        "interpretation_boundary": INTERPRETATION_BOUNDARIES[
                            "MECHANISM_HYPOTHESIS"
                        ],
                        "estimate_interval": {
                            "lower": None,
                            "point": None,
                            "upper": None,
                            "scale": "NOT_ESTIMATED",
                            "unit": "NONE",
                            "interval_kind": "NOT_ESTIMATED",
                        },
                        "window": {
                            "start_at": _time(created),
                            "end_at": packet["decision_at"],
                            "timeframe": "POINT_IN_TIME",
                            "sample_count": 1,
                        },
                        "lag": {"value": 0, "unit": "HOUR", "direction": "SYNCHRONOUS"},
                        "regime": {"regime_ids": [], "condition_refs": []},
                        "coverage": {"ratio": "1", "status": "COMPLETE", "limitations": []},
                        "stability": {
                            "assessment": "UNKNOWN",
                            "evidence_window_count": 1,
                            "break_refs": [],
                        },
                        "dependency_group_ids": ["EXACT_TYPED_ARTIFACT_PROJECTION"],
                        "provenance": [
                            {
                                "source_ref": spec["projection_id"],
                                "source_digest": envelope[
                                    "agent_authoring_envelope_digest"
                                ],
                                "observed_at": packet["decision_at"],
                                "available_at": packet["decision_at"],
                                "revision_ref": spec["delta_id"],
                            }
                        ],
                        "validity": {"valid_from": packet["decision_at"], "valid_until": None},
                        "identification_contract": None,
                        "status": "ACTIVE",
                        "created_at": packet["decision_at"],
                        "available_at": packet["decision_at"],
                        "limitations": [
                            "Structural projection only; no numerical or causal estimate."
                        ],
                    },
                    decision_at=packet["decision_at"],
                )
            )
        for key, previous_association in sorted(prior_associations.items()):
            if key in desired_edge_keys:
                continue
            source, target, relation = key
            if (
                source not in terminal_node_ids
                and target not in terminal_node_ids
                and relation
                not in {
                    "EVALUATES",
                    "PRODUCES",
                    "INSTANTIATES",
                    "SUPPORTS",
                    "OPPOSES",
                    "TRIGGERS",
                }
            ):
                # Immutable low-stage factual lineage remains active even
                # when the current cycle does not repeat that datum.
                continue
            associations.append(
                build_association_revision(
                    {
                        **{
                            field: value
                            for field, value in previous_association.items()
                            if field != "association_digest"
                        },
                        "revision": int(previous_association["revision"]) + 1,
                        "predecessor_digest": previous_association[
                            "association_digest"
                        ],
                        "status": "RETIRED",
                        "available_at": packet["decision_at"],
                        "validity": {
                            "valid_from": previous_association["validity"][
                                "valid_from"
                            ],
                            "valid_until": packet["decision_at"],
                        },
                        "window": {
                            **previous_association["window"],
                            "end_at": packet["decision_at"],
                        },
                    },
                    decision_at=packet["decision_at"],
                    prior_revision=previous_association,
                )
            )
        delta = build_graph_delta(
            {
                "schema_version": "V3_1_GRAPH_DELTA",
                "delta_id": spec["delta_id"],
                "graph_id": prior["graph_id"],
                "base_graph_revision": prior["revision"],
                "base_graph_digest": prior["graph_digest"],
                "revision": int(prior["revision"]) + 1,
                "occurred_at": packet["decision_at"],
                "available_at": packet["decision_at"],
                "node_revisions": nodes,
                "association_revisions": associations,
                "dependency_group_ids": sorted(
                    {
                        group
                        for row in [*nodes, *associations]
                        for group in row["dependency_group_ids"]
                    }
                ),
                "reason": spec["rationale"],
            },
            decision_at=packet["decision_at"],
            prior_graph=prior,
        )
        return prior, delta

    def compile(
        self,
        *,
        authoring_packet: Mapping[str, Any],
        authoring_envelope: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        validate_v31_proposal_authoring_packet(authoring_packet)
        validate_v31_agent_open_analysis_envelope(
            authoring_envelope, authoring_packet=authoring_packet
        )
        cycle_index = int(authoring_packet["cycle_index"])
        if cycle_index > 8:
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_COMPILER_CYCLE_OUTSIDE_FROZEN_CONTRACT"
            )
        bound = self._load_bound_inputs(authoring_packet)
        if cycle_index > int(
            bound["experiment"]["cycle_protocol"]["accepted_cycle_count"]
        ):
            raise V31SemanticCompilerError(
                "V31_SEMANTIC_COMPILER_CYCLE_OUTSIDE_EXPERIMENT"
            )
        previous = self._load_previous_state(
            packet=authoring_packet,
            envelope=authoring_envelope,
        )
        dataset = bound["dataset"]
        rows = point_in_time_dataset_rows_from_document(dataset)
        rows_by_id = {row.datum_id: row for row in rows}
        information_registry = build_information_event_revision_registry(
            run_id=authoring_packet["run_id"],
            cycle_index=cycle_index,
            decision_at=_moment(
                authoring_packet["decision_at"],
                "V31_SEMANTIC_DECISION_TIME_INVALID",
            ),
            admissions=tuple(bound["information_admissions"]),
            previous_registry=previous["information_registry"],
        )
        datum_registry = build_point_in_time_datum_revision_registry(
            run_id=authoring_packet["run_id"],
            cycle_index=cycle_index,
            decision_at=_moment(
                authoring_packet["decision_at"],
                "V31_SEMANTIC_DECISION_TIME_INVALID",
            ),
            dataset=dataset,
            previous_registry=previous["datum_registry"],
        )
        all_rows_by_id = {
            row.datum_id: row
            for row in (
                point_in_time_datum_from_document(document)
                for document in datum_registry["latest_revisions"]
            )
        }
        datum_bindings = {
            datum_id: row.to_document()["datum_digest"]
            for datum_id, row in all_rows_by_id.items()
            if row.to_document()["hypothesis_admissible"] is True
        }
        snapshot, dimensions, sentiment, sentiment_change = self._sentiment(
            packet=authoring_packet,
            envelope=authoring_envelope,
            dataset=dataset,
            rows_by_id=rows_by_id,
            previous_sentiment_state=previous["sentiment"],
        )
        registry, hypothesis_deltas, ledger, expectation_deltas = self._dynamic_state(
            packet=authoring_packet,
            envelope=authoring_envelope,
            datum_bindings=datum_bindings,
            previous_registry=previous["hypothesis_registry"],
            previous_ledger=previous["expectation_ledger"],
        )
        cloud = self._cloud(
            packet=authoring_packet,
            envelope=authoring_envelope,
            rows_by_id=rows_by_id,
            registry=registry,
            previous_cloud=previous["cloud"],
        )
        probability_cloud_transition_receipt = self._cloud_transition(
            packet=authoring_packet,
            envelope=authoring_envelope,
            rows_by_id=rows_by_id,
            previous_cloud=previous["cloud"],
            cloud=cloud,
        )
        paths = self._paths(
            packet=authoring_packet,
            envelope=authoring_envelope,
            rows_by_id=rows_by_id,
            ledger=ledger,
        )
        context, action_evaluation = self._actions(
            packet=authoring_packet,
            envelope=authoring_envelope,
            experiment=bound["experiment"],
            rows_by_id=rows_by_id,
            cloud=cloud,
        )
        prior_graph, graph_delta = self._graph(
            packet=authoring_packet,
            envelope=authoring_envelope,
            admissions=bound["information_admissions"],
            rows_by_id=rows_by_id,
            all_rows_by_id=all_rows_by_id,
            cloud=cloud,
            registry=registry,
            ledger=ledger,
            paths=paths,
            action_evaluation=action_evaluation,
            prior_graph=previous["graph"],
        )
        association_digests = sorted(
            row["association_estimation_receipt_digest"]
            for row in bound["association_receipts"]
        )
        inputs = seal_v31_inputs_receipt(
            run_id=authoring_packet["run_id"],
            cycle_index=cycle_index,
            decision_at=authoring_packet["decision_at"],
            symbol=authoring_packet["symbol"],
            information_event_digests=tuple(
                row.information_event_digest
                for row in bound["information_admissions"]
            ),
            information_revision_registry_digest=information_registry[
                "information_revision_registry_digest"
            ],
            association_estimation_receipt_digests=association_digests,
            pit_dataset_digest=dataset["dataset_digest"],
            datum_revision_registry_digest=datum_registry[
                "datum_revision_registry_digest"
            ],
            sentiment_state_digest=sentiment["sentiment_state_digest"],
            sentiment_change_digest=sentiment_change["sentiment_change_digest"],
            prior_graph_digest=prior_graph["graph_digest"],
            previous_accepted_state_digest=previous.get("accepted_digest"),
            previous_information_revision_registry_digest=(
                None
                if previous["information_registry"] is None
                else previous["information_registry"][
                    "information_revision_registry_digest"
                ]
            ),
            previous_pit_dataset_digest=(
                None
                if previous["pit_dataset"] is None
                else previous["pit_dataset"]["dataset_digest"]
            ),
            previous_datum_revision_registry_digest=(
                None
                if previous["datum_registry"] is None
                else previous["datum_registry"][
                    "datum_revision_registry_digest"
                ]
            ),
            previous_sentiment_state_digest=(
                None
                if previous["sentiment"] is None
                else previous["sentiment"]["sentiment_state_digest"]
            ),
            previous_hypothesis_registry_digest=(
                None
                if previous["hypothesis_registry"] is None
                else previous["hypothesis_registry"][
                    "hypothesis_registry_digest"
                ]
            ),
            previous_expectation_ledger_digest=(
                None
                if previous["expectation_ledger"] is None
                else previous["expectation_ledger"][
                    "expectation_ledger_digest"
                ]
            ),
            previous_probability_cloud_digest=(
                None
                if previous["cloud"] is None
                else previous["cloud"].to_document()["cloud_digest"]
            ),
            authority_snapshot_sha256=bound["authority_sha256"],
        )
        candidate_bindings = {
            row["candidate_id"]: canonical_digest(row)
            for row in action_evaluation["candidates"]
        }
        proposal = seal_v31_agent_proposal(
            inputs_receipt=inputs,
            sentiment_state_digest=sentiment["sentiment_state_digest"],
            sentiment_change_digest=sentiment_change["sentiment_change_digest"],
            graph_delta_digest=graph_delta["graph_delta_digest"],
            hypothesis_registry_digest=registry["hypothesis_registry_digest"],
            expectation_ledger_digest=ledger["expectation_ledger_digest"],
            probability_cloud_digest=cloud.to_document()["cloud_digest"],
            scenario_path_set_digest=paths.to_document()["path_set_digest"],
            candidate_bindings=candidate_bindings,
            information_interpretations=authoring_envelope[
                "information_interpretations"
            ],
            competing_explanations=authoring_envelope["competing_explanations"],
            unknowns=authoring_envelope["unknowns"],
            requested_observations=authoring_envelope["requested_observations"],
            hypothesis_novelty_rationales=authoring_envelope[
                "hypothesis_novelty_rationales"
            ],
            limitations=authoring_envelope["limitations"],
        )
        assembly = {
            "run_id": authoring_packet["run_id"],
            "cycle_index": cycle_index,
            "decision_at": authoring_packet["decision_at"],
            "symbol": authoring_packet["symbol"],
            "information_admissions": list(bound["information_admissions"]),
            "information_revision_registry": information_registry,
            "pit_dataset": dataset,
            "datum_revision_registry": datum_registry,
            "market_information_snapshot": snapshot,
            "sentiment_dimension_inputs": dimensions,
            "sentiment_state": sentiment,
            "sentiment_change": sentiment_change,
            "inputs_receipt": inputs,
            "agent_proposal": proposal,
            "authority_snapshot_sha256": bound["authority_sha256"],
            "prior_graph": prior_graph,
            "graph_delta": graph_delta,
            "hypothesis_registry": registry,
            "hypothesis_deltas": hypothesis_deltas,
            "expectation_ledger": ledger,
            "expectation_deltas": expectation_deltas,
            "probability_cloud": cloud,
            "scenario_paths": paths,
            "action_context": context,
            "action_evaluation": action_evaluation,
            "previous_accepted_state_digest": previous.get(
                "accepted_digest"
            ),
            "previous_information_revision_registry": previous[
                "information_registry"
            ],
            "previous_pit_dataset": previous["pit_dataset"],
            "previous_datum_revision_registry": previous["datum_registry"],
            "previous_sentiment_state": previous["sentiment"],
            "previous_probability_cloud": previous["cloud"],
            "probability_cloud_transition_receipt": (
                probability_cloud_transition_receipt
            ),
            "previous_hypothesis_registry": previous[
                "hypothesis_registry"
            ],
            "previous_expectation_ledger": previous["expectation_ledger"],
            "association_estimation_receipts": bound["association_receipts"],
        }
        return {
            "inputs_receipt": inputs,
            "agent_proposal": proposal,
            "assembly_inputs": assembly,
        }


__all__ = [
    "LocalV31SemanticCompiler",
    "V31BoundDocumentReader",
    "V31SemanticCompilerError",
]
