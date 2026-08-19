"""Contracts for Agent-authored V3.1 cycle analysis before compilation.

The durable Agent receives one content-addressed authoring packet containing
the exact source and authority bindings.  It returns an open analysis envelope,
not a pre-built ``agent_proposal`` receipt and never a selection.  A separate
Application compiler must turn the envelope into the existing typed V3.1
artifacts and replay ``assemble_v31_cycle_evaluation`` before selection can be
unblocked.

These contracts intentionally do not invent numerical probabilities.  The
probability cloud specification is ordinal and must retain OTHER and UNKNOWN.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .dynamic_research import V31_SENTIMENT_AXES


class V31CycleAuthoringError(ValueError):
    """An authoring packet, envelope, or compilation receipt failed closed."""


AUTHORING_PACKET_SCHEMA_ID = "theory_paper_v31_proposal_authoring_packet"
AUTHORING_ENVELOPE_SCHEMA_ID = "theory_paper_v31_agent_open_analysis_envelope"
AUTHORING_COMPILATION_SCHEMA_ID = (
    "theory_paper_v31_agent_authoring_compilation_receipt"
)
AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID = (
    "theory_paper_v31_authoring_compilation_admission"
)
AUTHORING_PACKET_DIGEST_FIELD = "authoring_packet_digest"
AUTHORING_ENVELOPE_DIGEST_FIELD = "agent_authoring_envelope_digest"
AUTHORING_COMPILATION_DIGEST_FIELD = "authoring_compilation_receipt_digest"
AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD = (
    "authoring_compilation_admission_digest"
)
COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID = (
    "theory_paper_v31_compiled_assembly_bundle"
)
COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD = "compiled_assembly_bundle_digest"

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_PREVIOUS_HEAD_SCHEMAS = {
    "previous_accepted_state": (
        "theory_paper_v2_v31_accepted_research_state",
        "accepted_state_digest",
    ),
    "previous_information_revision_registry": (
        "theory_paper_v2_v31_information_revision_registry",
        "information_revision_registry_digest",
    ),
    "previous_pit_dataset": (
        "theory_paper_v2_v31_point_in_time_dataset",
        "dataset_digest",
    ),
    "previous_datum_revision_registry": (
        "theory_paper_v2_v31_datum_revision_registry",
        "datum_revision_registry_digest",
    ),
    "previous_sentiment_state": (
        "theory_paper_v2_v31_multidimensional_market_sentiment_state",
        "sentiment_state_digest",
    ),
    "previous_hypothesis_registry": (
        "dynamic_hypothesis_registry",
        "hypothesis_registry_digest",
    ),
    "previous_expectation_ledger": (
        "append_only_expectation_ledger",
        "expectation_ledger_digest",
    ),
    "previous_probability_cloud": (
        "theory_paper_v2_v31_probability_cloud",
        "cloud_digest",
    ),
}
_PACKET_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        "cycle_source_admission_binding",
        "source_qualification_completion_binding",
        "information_event_bindings",
        "pit_dataset_binding",
        "association_estimation_receipt_bindings",
        "previous_head_bindings",
        "authoring_purpose",
        "authority_context",
        "analysis_policy",
        "source_boundary",
        "source_material_must_be_read_before_analysis",
        "qualification_evidence_is_start_authority",
        "authority_binding_separate",
        "selection_fields_admitted",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        AUTHORING_PACKET_DIGEST_FIELD,
    }
)
_AUTHORITY_CONTEXT_FIELDS = frozenset(
    {
        "mode",
        "theory_approval_binding",
        "experiment_subject_binding",
        "active_authority_binding",
        "experiment_start_authorized",
    }
)
_AUTHORING_PURPOSES = frozenset(
    {"TRANSPORT_QUALIFICATION_ONLY", "AUTHORIZED_RESEARCH_CYCLE"}
)
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "decision_at",
        "symbol",
        AUTHORING_PACKET_DIGEST_FIELD,
        "semantic_specification_version",
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
        "proposal_phase",
        "probability_representation",
        "selection_fields_admitted",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        AUTHORING_ENVELOPE_DIGEST_FIELD,
    }
)
_SENTIMENT_ROW_FIELDS = frozenset(
    {
        "axis",
        "ordinal_state",
        "evidence_assessments",
        "required_dependency_groups",
        "timeframe_states",
        "reasoning",
        "limitations",
        "next_discriminating_observation",
    }
)
_SENTIMENT_EVIDENCE_FIELDS = frozenset(
    {"evidence_ref", "ordinal_contribution", "rule", "direction"}
)
_CLOUD_FIELDS = frozenset(
    {"mode", "horizon", "components", "unknown_refs", "limitations"}
)
_CLOUD_COMPONENT_FIELDS = frozenset(
    {
        "hypothesis_id",
        "plausibility",
        "evidence_refs",
        "opposition_refs",
        "conflict_refs",
        "dependency_groups",
        "data_uncertainty",
        "model_uncertainty",
        "sensitivity_notes",
    }
)
_SCENARIO_SET_FIELDS = frozenset(
    {"set_id", "lead_path_id", "runner_up_path_id", "residual_path_id", "paths"}
)
_ACTION_SPEC_FIELDS = frozenset(
    {
        "candidate_id",
        "action",
        "scale_pct",
        "target_role",
        "path_refs",
        "evidence_refs",
        "trigger_conditions",
        "invalidation_conditions",
        "risk_refs",
        "thesis",
        "wait_reason",
        "opportunity_cost",
        "next_observation",
        "next_review_at",
        "information_not_arrived_default",
        "position_protection_responsibility",
    }
)
_GRAPH_SPEC_FIELDS = frozenset(
    {
        "projection_id",
        "graph_id",
        "delta_id",
        "projection_policy",
        "additional_associations",
        "rationale",
    }
)
_SCENARIO_PATH_SPEC_FIELDS = frozenset(
    {
        "path_id",
        "triggers",
        "guards",
        "unless",
        "transition",
        "mechanism",
        "mechanism_hypothesis_refs",
        "expectations",
        "falsifiers",
        "else_path_refs",
        "preserves_other_unknown",
        "action_implications",
        "expires_at",
        "next_review_at",
        "next_observation",
        "regime_refs",
        "probability_cloud_refs",
    }
)
_PATH_PREDICATE_SPEC_FIELDS = frozenset(
    {
        "predicate_id",
        "fact_ref",
        "timing",
        "operator",
        "expected",
        "available_at",
        "minimum_quality",
        "minimum_coverage",
        "allowed_conflict_states",
        "limitations",
    }
)
_PATH_EXPECTATION_SPEC_FIELDS = frozenset(
    {
        "observation_id",
        "hypothesis_id",
        "observable_ref",
        "horizon_at",
        "direction_or_state",
        "confirms_when",
        "contradicts_when",
    }
)
_PATH_ACTION_IMPLICATION_SPEC_FIELDS = frozenset(
    {"action", "effect", "rationale", "risk_refs", "opportunity_cost"}
)
_COMPILATION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "compiled_at",
        AUTHORING_PACKET_DIGEST_FIELD,
        AUTHORING_ENVELOPE_DIGEST_FIELD,
        "inputs_receipt_digest",
        "agent_proposal_digest",
        "action_evaluation_digest",
        "preselection_digest",
        "compiler_id",
        "deterministic_replay_passed",
        "selection_fields_admitted",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        AUTHORING_COMPILATION_DIGEST_FIELD,
    }
)
_COMPILATION_ADMISSION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "admitted_at",
        "compiler_id",
        "authoring_packet_binding",
        "proposal_attempt_binding",
        "proposal_request_binding",
        "proposal_claim_binding",
        "proposal_delivery_binding",
        "proposal_consume_binding",
        "inputs_receipt_binding",
        "agent_proposal_binding",
        "action_evaluation_binding",
        "preselection_binding",
        "compilation_receipt_binding",
        "compiled_assembly_bundle_binding",
        "deterministic_replay_passed",
        "selection_unblocked",
        "selection_performed",
        "chat_history_is_authority",
        "external_execution_authority",
        "executable",
        AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    }
)
_ORDINAL_SENTIMENT_STATES = frozenset(
    {
        "STRONG_NEGATIVE",
        "NEGATIVE",
        "MIXED",
        "NEUTRAL",
        "POSITIVE",
        "STRONG_POSITIVE",
        "UNKNOWN",
    }
)
_PLAUSIBILITY_LEVELS = frozenset({"HIGH", "MEDIUM", "LOW", "UNKNOWN"})
_LEGAL_FLAT_ACTIONS = frozenset({"WAIT", "OPEN_LONG", "OPEN_SHORT"})
_FORBIDDEN_SELECTION_KEYS = frozenset(
    {
        "selected",
        "selected_action",
        "selected_candidate_id",
        "action_selection",
        "action_selection_digest",
        "authorized_action",
        "execution_authority",
        "order",
        "order_payload",
    }
)
_FORBIDDEN_NUMERIC_PROBABILITY_KEYS = frozenset(
    {
        "probability",
        "probability_pct",
        "probability_percent",
        "weight",
        "weights",
        "margin",
        "entropy",
        "expected_value",
        "expected_value_usdt",
        "ev",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise V31CycleAuthoringError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31CycleAuthoringError(code)
    return value


def _timestamp(value: Any, code: str) -> str:
    value = _text(value, code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31CycleAuthoringError(code) from exc
    if parsed.tzinfo is None:
        raise V31CycleAuthoringError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != value:
        raise V31CycleAuthoringError(code)
    return value


def _cycle(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise V31CycleAuthoringError("V31_AUTHORING_CYCLE_INDEX_INVALID")
    return value


def _strings(
    value: Any, code: str, *, allow_empty: bool = False, sort: bool = False
) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise V31CycleAuthoringError(code)
    rows = list(value)
    if (
        (not allow_empty and not rows)
        or any(not isinstance(row, str) or not row.strip() for row in rows)
        or len(rows) != len(set(rows))
    ):
        raise V31CycleAuthoringError(code)
    normalized = [row.strip() for row in rows]
    return sorted(normalized) if sort else normalized


def _verify_self(document: Mapping[str, Any], field: str, code: str) -> str:
    try:
        return verify_self_digest(document, field)
    except (AttributeError, TypeError, ValueError) as exc:
        raise V31CycleAuthoringError(code) from exc


def _contains_key(value: Any, forbidden: frozenset[str]) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and key.casefold() in forbidden:
                return True
            if _contains_key(nested, forbidden):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_key(row, forbidden) for row in value)
    return False


def validate_v31_authoring_binding(
    binding: Any,
    *,
    expected_schema_id: str | None = None,
    expected_digest_field: str | None = None,
) -> dict[str, str]:
    if not isinstance(binding, Mapping) or set(binding) != _BINDING_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_BINDING_INVALID")
    relative_ref = _text(
        binding.get("relative_ref"), "V31_AUTHORING_BINDING_INVALID"
    )
    path = PurePosixPath(relative_ref)
    if (
        "\\" in relative_ref
        or path.as_posix() != relative_ref
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_BINDING_INVALID")
    schema_id = _text(binding.get("schema_id"), "V31_AUTHORING_BINDING_INVALID")
    digest_field = _text(
        binding.get("digest_field"), "V31_AUTHORING_BINDING_INVALID"
    )
    if (
        expected_schema_id is not None
        and schema_id != expected_schema_id
    ) or (
        expected_digest_field is not None
        and digest_field != expected_digest_field
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_BINDING_INVALID")
    return {
        "relative_ref": relative_ref,
        "schema_id": schema_id,
        "digest_field": digest_field,
        "semantic_digest": _digest(
            binding.get("semantic_digest"), "V31_AUTHORING_BINDING_INVALID"
        ),
        "physical_sha256": _digest(
            binding.get("physical_sha256"), "V31_AUTHORING_BINDING_INVALID"
        ),
    }


def _analysis_policy() -> dict[str, Any]:
    return {
        "sentiment_axes": list(V31_SENTIMENT_AXES),
        "probability_representation": (
            "ORDINAL_PLAUSIBILITY_WITH_OTHER_UNKNOWN_NO_NUMERIC_PROBABILITY"
        ),
        "legal_flat_action_universe": sorted(_LEGAL_FLAT_ACTIONS),
        "agent_authors_open_hypotheses": True,
        "agent_authors_scenarios": True,
        "agent_authors_action_candidates_not_selection": True,
        "application_compiles_and_replays_typed_artifacts": True,
        "selection_after_complete_evaluation_seal": True,
    }


def seal_v31_proposal_authoring_packet(
    *,
    run_id: str,
    cycle_index: int,
    decision_at: str,
    symbol: str,
    cycle_source_admission_binding: Mapping[str, Any] | None,
    source_qualification_completion_binding: Mapping[str, Any],
    information_event_bindings: Sequence[Mapping[str, Any]],
    pit_dataset_binding: Mapping[str, Any],
    authoring_purpose: str,
    theory_approval_binding: Mapping[str, Any],
    experiment_subject_binding: Mapping[str, Any],
    active_authority_binding: Mapping[str, Any] | None,
    previous_head_bindings: Mapping[str, Mapping[str, Any] | None],
    association_estimation_receipt_bindings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Seal the exact evidence and authority visible to the proposal Agent."""

    cycle = _cycle(cycle_index)
    events = [
        validate_v31_authoring_binding(
            row,
            expected_schema_id=(
                "theory_paper_v31_source_qualification_information_event"
            ),
            expected_digest_field=(
                "source_qualification_information_event_record_digest"
            ),
        )
        for row in information_event_bindings
    ]
    if not events or len({row["relative_ref"] for row in events}) != len(events):
        raise V31CycleAuthoringError("V31_AUTHORING_INFORMATION_BINDINGS_INVALID")
    associations = [
        validate_v31_authoring_binding(
            row,
            expected_schema_id=(
                "theory_paper_v2_v31_association_estimation_receipt"
            ),
            expected_digest_field="association_estimation_receipt_digest",
        )
        for row in association_estimation_receipt_bindings
    ]
    if len({row["relative_ref"] for row in associations}) != len(associations):
        raise V31CycleAuthoringError("V31_AUTHORING_ASSOCIATION_BINDINGS_INVALID")
    if not isinstance(previous_head_bindings, Mapping) or set(
        previous_head_bindings
    ) != set(_PREVIOUS_HEAD_SCHEMAS):
        raise V31CycleAuthoringError("V31_AUTHORING_PREVIOUS_HEADS_INVALID")
    heads: dict[str, dict[str, str] | None] = {}
    for key, expected in _PREVIOUS_HEAD_SCHEMAS.items():
        raw = previous_head_bindings[key]
        heads[key] = (
            None
            if raw is None
            else validate_v31_authoring_binding(
                raw,
                expected_schema_id=expected[0],
                expected_digest_field=expected[1],
            )
        )
    if cycle == 1 and any(value is not None for value in heads.values()):
        raise V31CycleAuthoringError("V31_AUTHORING_GENESIS_PREVIOUS_HEAD_FORBIDDEN")
    if cycle > 1 and any(value is None for value in heads.values()):
        raise V31CycleAuthoringError("V31_AUTHORING_PREVIOUS_HEAD_REQUIRED")
    purpose = _text(
        authoring_purpose, "V31_AUTHORING_PURPOSE_INVALID"
    )
    if purpose not in _AUTHORING_PURPOSES:
        raise V31CycleAuthoringError("V31_AUTHORING_PURPOSE_INVALID")
    approval = validate_v31_authoring_binding(
        theory_approval_binding,
        expected_schema_id="theory_paper_v31_user_approval_receipt",
        expected_digest_field="approval_receipt_digest",
    )
    subject = validate_v31_authoring_binding(
        experiment_subject_binding,
        expected_schema_id="theory_paper_v2_v31_minimal_experiment_contract",
        expected_digest_field="experiment_contract_digest",
    )
    if purpose == "TRANSPORT_QUALIFICATION_ONLY":
        if (
            active_authority_binding is not None
            or cycle_source_admission_binding is not None
        ):
            raise V31CycleAuthoringError(
                "V31_AUTHORING_QUALIFICATION_AUTHORITY_OR_SOURCE_ADMISSION_FORBIDDEN"
            )
        source_admission = None
        authority_context = {
            "mode": "PRESTART_APPROVAL_AND_EXPERIMENT_SUBJECT",
            "theory_approval_binding": approval,
            "experiment_subject_binding": subject,
            "active_authority_binding": None,
            "experiment_start_authorized": False,
        }
    else:
        if active_authority_binding is None:
            raise V31CycleAuthoringError(
                "V31_AUTHORING_ACTIVE_AUTHORITY_REQUIRED"
            )
        if cycle_source_admission_binding is None:
            raise V31CycleAuthoringError(
                "V31_AUTHORING_CYCLE_SOURCE_ADMISSION_REQUIRED"
            )
        source_admission = validate_v31_authoring_binding(
            cycle_source_admission_binding,
            expected_schema_id="theory_paper_v31_cycle_source_admission",
            expected_digest_field="cycle_source_admission_digest",
        )
        authority_context = {
            "mode": "ACTIVE_RESEARCH_AUTHORITY",
            "theory_approval_binding": approval,
            "experiment_subject_binding": subject,
            "active_authority_binding": validate_v31_authoring_binding(
                active_authority_binding,
                expected_schema_id=(
                    "theory_paper_v31_current_research_authority"
                ),
                expected_digest_field="authority_digest",
            ),
            "experiment_start_authorized": True,
        }
    if set(authority_context) != _AUTHORITY_CONTEXT_FIELDS:  # pragma: no cover
        raise V31CycleAuthoringError("V31_AUTHORING_AUTHORITY_CONTEXT_INVALID")
    return self_digest(
        {
            "schema_id": AUTHORING_PACKET_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": _text(run_id, "V31_AUTHORING_RUN_ID_INVALID"),
            "cycle_index": cycle,
            "decision_at": _timestamp(
                decision_at, "V31_AUTHORING_DECISION_AT_INVALID"
            ),
            "symbol": _text(symbol, "V31_AUTHORING_SYMBOL_INVALID"),
            "cycle_source_admission_binding": source_admission,
            "source_qualification_completion_binding": (
                validate_v31_authoring_binding(
                    source_qualification_completion_binding,
                    expected_schema_id=(
                        "theory_paper_v31_source_qualification_completion"
                    ),
                    expected_digest_field=(
                        "source_qualification_completion_digest"
                    ),
                )
            ),
            "information_event_bindings": sorted(
                events, key=lambda row: row["relative_ref"]
            ),
            "pit_dataset_binding": validate_v31_authoring_binding(
                pit_dataset_binding,
                expected_schema_id=(
                    "theory_paper_v2_v31_point_in_time_dataset"
                ),
                expected_digest_field="dataset_digest",
            ),
            "association_estimation_receipt_bindings": sorted(
                associations, key=lambda row: row["relative_ref"]
            ),
            "previous_head_bindings": heads,
            "authoring_purpose": purpose,
            "authority_context": authority_context,
            "analysis_policy": _analysis_policy(),
            "source_boundary": "QUALIFIED_PUBLIC_POINT_IN_TIME_READ_ONLY",
            "source_material_must_be_read_before_analysis": True,
            "qualification_evidence_is_start_authority": False,
            "authority_binding_separate": True,
            "selection_fields_admitted": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        AUTHORING_PACKET_DIGEST_FIELD,
    )


def validate_v31_proposal_authoring_packet(document: Mapping[str, Any]) -> str:
    digest = _verify_self(
        document,
        AUTHORING_PACKET_DIGEST_FIELD,
        "V31_AUTHORING_PACKET_DIGEST_INVALID",
    )
    if not isinstance(document, Mapping) or set(document) != _PACKET_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_PACKET_SCHEMA_INVALID")
    rebuilt = seal_v31_proposal_authoring_packet(
        run_id=document["run_id"],
        cycle_index=document["cycle_index"],
        decision_at=document["decision_at"],
        symbol=document["symbol"],
        cycle_source_admission_binding=document[
            "cycle_source_admission_binding"
        ],
        source_qualification_completion_binding=document[
            "source_qualification_completion_binding"
        ],
        information_event_bindings=document["information_event_bindings"],
        pit_dataset_binding=document["pit_dataset_binding"],
        association_estimation_receipt_bindings=document[
            "association_estimation_receipt_bindings"
        ],
        previous_head_bindings=document["previous_head_bindings"],
        authoring_purpose=document["authoring_purpose"],
        theory_approval_binding=document["authority_context"][
            "theory_approval_binding"
        ],
        experiment_subject_binding=document["authority_context"][
            "experiment_subject_binding"
        ],
        active_authority_binding=document["authority_context"][
            "active_authority_binding"
        ],
    )
    if rebuilt != dict(document) or digest != rebuilt[AUTHORING_PACKET_DIGEST_FIELD]:
        raise V31CycleAuthoringError("V31_AUTHORING_PACKET_NOT_CANONICAL")
    return digest


def _sentiment_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise V31CycleAuthoringError("V31_AUTHORING_SENTIMENT_INVALID")
    by_axis: dict[str, dict[str, Any]] = {}
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _SENTIMENT_ROW_FIELDS:
            raise V31CycleAuthoringError("V31_AUTHORING_SENTIMENT_INVALID")
        axis = _text(raw.get("axis"), "V31_AUTHORING_SENTIMENT_INVALID")
        state = _text(
            raw.get("ordinal_state"), "V31_AUTHORING_SENTIMENT_INVALID"
        )
        if axis in by_axis or state not in _ORDINAL_SENTIMENT_STATES:
            raise V31CycleAuthoringError("V31_AUTHORING_SENTIMENT_INVALID")
        raw_evidence = raw.get("evidence_assessments")
        if (
            not isinstance(raw_evidence, Sequence)
            or isinstance(raw_evidence, (str, bytes))
        ):
            raise V31CycleAuthoringError("V31_AUTHORING_SENTIMENT_INVALID")
        evidence: list[dict[str, Any]] = []
        evidence_refs: set[str] = set()
        for assessment in raw_evidence:
            if (
                not isinstance(assessment, Mapping)
                or set(assessment) != _SENTIMENT_EVIDENCE_FIELDS
            ):
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_SENTIMENT_EVIDENCE_INVALID"
                )
            evidence_ref = _text(
                assessment.get("evidence_ref"),
                "V31_AUTHORING_SENTIMENT_EVIDENCE_INVALID",
            )
            contribution = assessment.get("ordinal_contribution")
            direction = assessment.get("direction")
            if (
                evidence_ref in evidence_refs
                or isinstance(contribution, bool)
                or not isinstance(contribution, int)
                or contribution not in {-2, -1, 0, 1, 2}
                or direction
                != (
                    "NEGATIVE"
                    if contribution < 0
                    else "POSITIVE"
                    if contribution > 0
                    else "NEUTRAL"
                )
            ):
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_SENTIMENT_EVIDENCE_INVALID"
                )
            evidence_refs.add(evidence_ref)
            evidence.append(
                {
                    "evidence_ref": evidence_ref,
                    "ordinal_contribution": contribution,
                    "rule": _text(
                        assessment.get("rule"),
                        "V31_AUTHORING_SENTIMENT_EVIDENCE_INVALID",
                    ),
                    "direction": direction,
                }
            )
        if state == "UNKNOWN" and evidence:
            raise V31CycleAuthoringError(
                "V31_AUTHORING_UNKNOWN_SENTIMENT_EVIDENCE_FORBIDDEN"
            )
        if state != "UNKNOWN" and not evidence:
            raise V31CycleAuthoringError(
                "V31_AUTHORING_SENTIMENT_EVIDENCE_REQUIRED"
            )
        required_groups = _strings(
            raw.get("required_dependency_groups"),
            "V31_AUTHORING_SENTIMENT_REQUIRED_GROUPS_INVALID",
            sort=True,
        )
        timeframes = raw.get("timeframe_states")
        if (
            not isinstance(timeframes, Mapping)
            or not timeframes
            or any(
                not isinstance(key, str)
                or not key.strip()
                or (
                    row is not None
                    and (
                        isinstance(row, bool)
                        or not isinstance(row, int)
                        or row not in {-2, -1, 0, 1, 2}
                    )
                )
                for key, row in timeframes.items()
            )
        ):
            raise V31CycleAuthoringError(
                "V31_AUTHORING_SENTIMENT_TIMEFRAMES_INVALID"
            )
        by_axis[axis] = {
            "axis": axis,
            "ordinal_state": state,
            "evidence_assessments": sorted(
                evidence, key=lambda row: row["evidence_ref"]
            ),
            "required_dependency_groups": required_groups,
            "timeframe_states": dict(sorted(timeframes.items())),
            "reasoning": _text(
                raw.get("reasoning"), "V31_AUTHORING_SENTIMENT_INVALID"
            ),
            "limitations": _strings(
                raw.get("limitations"), "V31_AUTHORING_SENTIMENT_INVALID"
            ),
            "next_discriminating_observation": _text(
                raw.get("next_discriminating_observation"),
                "V31_AUTHORING_SENTIMENT_INVALID",
            ),
        }
    if set(by_axis) != set(V31_SENTIMENT_AXES):
        raise V31CycleAuthoringError("V31_AUTHORING_SENTIMENT_AXES_INCOMPLETE")
    return [by_axis[axis] for axis in V31_SENTIMENT_AXES]


def _probability_cloud_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CLOUD_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_SPEC_INVALID")
    if value.get("mode") != "SUBJECTIVE_PLAUSIBILITY":
        raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_MODE_INVALID")
    raw_components = value.get("components")
    if (
        not isinstance(raw_components, Sequence)
        or isinstance(raw_components, (str, bytes))
        or not raw_components
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_SPEC_INVALID")
    components: list[dict[str, Any]] = []
    ids: set[str] = set()
    for raw in raw_components:
        if not isinstance(raw, Mapping) or set(raw) != _CLOUD_COMPONENT_FIELDS:
            raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_COMPONENT_INVALID")
        hypothesis_id = _text(
            raw.get("hypothesis_id"), "V31_AUTHORING_CLOUD_COMPONENT_INVALID"
        )
        plausibility = _text(
            raw.get("plausibility"), "V31_AUTHORING_CLOUD_COMPONENT_INVALID"
        )
        if hypothesis_id in ids or plausibility not in _PLAUSIBILITY_LEVELS:
            raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_COMPONENT_INVALID")
        ids.add(hypothesis_id)
        components.append(
            {
                "hypothesis_id": hypothesis_id,
                "plausibility": plausibility,
                "evidence_refs": _strings(
                    raw.get("evidence_refs"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "opposition_refs": _strings(
                    raw.get("opposition_refs"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "conflict_refs": _strings(
                    raw.get("conflict_refs"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "dependency_groups": _strings(
                    raw.get("dependency_groups"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "data_uncertainty": _strings(
                    raw.get("data_uncertainty"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "model_uncertainty": _strings(
                    raw.get("model_uncertainty"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                    allow_empty=True,
                    sort=True,
                ),
                "sensitivity_notes": _strings(
                    raw.get("sensitivity_notes"),
                    "V31_AUTHORING_CLOUD_COMPONENT_INVALID",
                ),
            }
        )
    if not {"OTHER", "UNKNOWN"}.issubset(ids):
        raise V31CycleAuthoringError("V31_AUTHORING_CLOUD_RESIDUALS_REQUIRED")
    return {
        "mode": "SUBJECTIVE_PLAUSIBILITY",
        "horizon": _text(value.get("horizon"), "V31_AUTHORING_CLOUD_SPEC_INVALID"),
        "components": sorted(components, key=lambda row: row["hypothesis_id"]),
        "unknown_refs": _strings(
            value.get("unknown_refs"), "V31_AUTHORING_CLOUD_SPEC_INVALID"
        ),
        "limitations": _strings(
            value.get("limitations"), "V31_AUTHORING_CLOUD_SPEC_INVALID"
        ),
    }


def _scenario_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SCENARIO_SET_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_SCENARIO_SPEC_INVALID")
    paths = value.get("paths")
    if (
        not isinstance(paths, Sequence)
        or isinstance(paths, (str, bytes))
        or not paths
        or any(not isinstance(row, Mapping) for row in paths)
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_SCENARIO_SPEC_INVALID")
    copied = [dict(row) for row in paths]
    for row in copied:
        if set(row) != _SCENARIO_PATH_SPEC_FIELDS:
            raise V31CycleAuthoringError(
                "V31_AUTHORING_SCENARIO_PATH_SCHEMA_INVALID"
            )
        for predicate_group in ("triggers", "guards", "unless", "falsifiers"):
            predicates = row.get(predicate_group)
            if (
                not isinstance(predicates, Sequence)
                or isinstance(predicates, (str, bytes))
                or (predicate_group != "unless" and not predicates)
                or any(
                    not isinstance(predicate, Mapping)
                    or set(predicate) != _PATH_PREDICATE_SPEC_FIELDS
                    for predicate in predicates
                )
            ):
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_SCENARIO_PREDICATE_SCHEMA_INVALID"
                )
        expectations = row.get("expectations")
        implications = row.get("action_implications")
        if (
            not isinstance(expectations, Sequence)
            or isinstance(expectations, (str, bytes))
            or not expectations
            or any(
                not isinstance(expectation, Mapping)
                or set(expectation) != _PATH_EXPECTATION_SPEC_FIELDS
                for expectation in expectations
            )
            or not isinstance(implications, Sequence)
            or isinstance(implications, (str, bytes))
            or not implications
            or any(
                not isinstance(implication, Mapping)
                or set(implication) != _PATH_ACTION_IMPLICATION_SPEC_FIELDS
                for implication in implications
            )
        ):
            raise V31CycleAuthoringError(
                "V31_AUTHORING_SCENARIO_SEMANTICS_INCOMPLETE"
            )
    path_ids = [row.get("path_id") for row in copied]
    if (
        any(not isinstance(path_id, str) or not path_id.strip() for path_id in path_ids)
        or len(path_ids) != len(set(path_ids))
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_SCENARIO_PATH_IDS_INVALID")
    lead = _text(value.get("lead_path_id"), "V31_AUTHORING_SCENARIO_SPEC_INVALID")
    runner = _text(
        value.get("runner_up_path_id"), "V31_AUTHORING_SCENARIO_SPEC_INVALID"
    )
    residual = _text(
        value.get("residual_path_id"), "V31_AUTHORING_SCENARIO_SPEC_INVALID"
    )
    if (
        residual != "OTHER"
        or len({lead, runner, residual}) != 3
        or not {lead, runner, residual}.issubset(set(path_ids))
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_SCENARIO_COMPETITION_INVALID")
    return {
        "set_id": _text(value.get("set_id"), "V31_AUTHORING_SCENARIO_SPEC_INVALID"),
        "lead_path_id": lead,
        "runner_up_path_id": runner,
        "residual_path_id": residual,
        "paths": sorted(copied, key=lambda row: str(row["path_id"])),
    }


def _action_specs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise V31CycleAuthoringError("V31_AUTHORING_ACTION_SPECS_INVALID")
    rows: list[dict[str, Any]] = []
    ids: set[str] = set()
    actions: set[str] = set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != _ACTION_SPEC_FIELDS:
            raise V31CycleAuthoringError("V31_AUTHORING_ACTION_SPEC_INVALID")
        candidate_id = _text(
            raw.get("candidate_id"), "V31_AUTHORING_ACTION_SPEC_INVALID"
        )
        action = _text(raw.get("action"), "V31_AUTHORING_ACTION_SPEC_INVALID")
        if candidate_id in ids or action not in _LEGAL_FLAT_ACTIONS:
            raise V31CycleAuthoringError("V31_AUTHORING_ACTION_SPEC_INVALID")
        ids.add(candidate_id)
        actions.add(action)
        row = {
            "candidate_id": candidate_id,
            "action": action,
            "scale_pct": raw.get("scale_pct"),
            "target_role": raw.get("target_role"),
            "path_refs": _strings(
                raw.get("path_refs"), "V31_AUTHORING_ACTION_SPEC_INVALID", sort=True
            ),
            "evidence_refs": _strings(
                raw.get("evidence_refs"),
                "V31_AUTHORING_ACTION_SPEC_INVALID",
                sort=True,
            ),
            "trigger_conditions": _strings(
                raw.get("trigger_conditions"), "V31_AUTHORING_ACTION_SPEC_INVALID"
            ),
            "invalidation_conditions": _strings(
                raw.get("invalidation_conditions"),
                "V31_AUTHORING_ACTION_SPEC_INVALID",
            ),
            "risk_refs": _strings(
                raw.get("risk_refs"), "V31_AUTHORING_ACTION_SPEC_INVALID", sort=True
            ),
            "thesis": _text(raw.get("thesis"), "V31_AUTHORING_ACTION_SPEC_INVALID"),
            "wait_reason": raw.get("wait_reason"),
            "opportunity_cost": raw.get("opportunity_cost"),
            "next_observation": raw.get("next_observation"),
            "next_review_at": raw.get("next_review_at"),
            "information_not_arrived_default": raw.get(
                "information_not_arrived_default"
            ),
            "position_protection_responsibility": raw.get(
                "position_protection_responsibility"
            ),
        }
        optional = (
            "wait_reason",
            "opportunity_cost",
            "next_observation",
            "next_review_at",
        )
        if action == "WAIT":
            if row["scale_pct"] is not None or row["target_role"] is not None:
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_WAIT_SCALE_OR_ROLE_FORBIDDEN"
                )
            for field in optional:
                if field == "next_review_at":
                    _timestamp(row[field], "V31_AUTHORING_WAIT_FIELDS_INVALID")
                else:
                    _text(row[field], "V31_AUTHORING_WAIT_FIELDS_INVALID")
            for field in (
                "information_not_arrived_default",
                "position_protection_responsibility",
            ):
                _text(row[field], "V31_AUTHORING_WAIT_FIELDS_INVALID")
        else:
            if any(row[field] is not None for field in optional) or any(
                row[field] is not None
                for field in (
                    "information_not_arrived_default",
                    "position_protection_responsibility",
                )
            ):
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_NON_WAIT_FIELDS_INVALID"
                )
            if (
                isinstance(row["scale_pct"], bool)
                or not isinstance(row["scale_pct"], int)
                or row["scale_pct"] <= 0
                or row["scale_pct"] > 100
                or row["target_role"] not in {"CORE", "TACTICAL"}
            ):
                raise V31CycleAuthoringError(
                    "V31_AUTHORING_ENTRY_SCALE_OR_ROLE_INVALID"
                )
        rows.append(row)
    if actions != _LEGAL_FLAT_ACTIONS:
        raise V31CycleAuthoringError("V31_AUTHORING_LEGAL_ACTION_SET_INCOMPLETE")
    return sorted(rows, key=lambda row: row["candidate_id"])


def seal_v31_agent_open_analysis_envelope(
    *,
    authoring_packet: Mapping[str, Any],
    information_interpretations: Sequence[str],
    operational_synthesis: str,
    sentiment_axis_analyses: Sequence[Mapping[str, Any]],
    graph_delta_spec: Mapping[str, Any],
    hypothesis_deltas: Sequence[Mapping[str, Any]],
    expectation_deltas: Sequence[Mapping[str, Any]],
    probability_cloud_spec: Mapping[str, Any],
    scenario_path_set_spec: Mapping[str, Any],
    action_candidate_specs: Sequence[Mapping[str, Any]],
    competing_explanations: Sequence[str],
    unknowns: Sequence[str],
    requested_observations: Sequence[str],
    hypothesis_novelty_rationales: Mapping[str, str],
    limitations: Sequence[str],
) -> dict[str, Any]:
    """Seal Agent-authored open analysis with no selection or execution power."""

    packet_digest = validate_v31_proposal_authoring_packet(authoring_packet)
    graph = dict(graph_delta_spec) if isinstance(graph_delta_spec, Mapping) else None
    hypotheses = (
        [dict(row) for row in hypothesis_deltas]
        if isinstance(hypothesis_deltas, Sequence)
        and not isinstance(hypothesis_deltas, (str, bytes))
        and hypothesis_deltas
        and all(isinstance(row, Mapping) for row in hypothesis_deltas)
        else None
    )
    expectations = (
        [dict(row) for row in expectation_deltas]
        if isinstance(expectation_deltas, Sequence)
        and not isinstance(expectation_deltas, (str, bytes))
        and expectation_deltas
        and all(isinstance(row, Mapping) for row in expectation_deltas)
        else None
    )
    if (
        not isinstance(graph, dict)
        or set(graph) != _GRAPH_SPEC_FIELDS
        or graph.get("projection_policy")
        != "EXACT_TYPED_ARTIFACT_VERTICAL_PROJECTION_V1"
        or not isinstance(graph.get("additional_associations"), list)
        or graph["additional_associations"]
        or any(
            not isinstance(graph.get(field), str) or not graph[field].strip()
            for field in ("projection_id", "graph_id", "delta_id")
        )
        or not isinstance(graph["rationale"], str)
        or not graph["rationale"].strip()
        or hypotheses is None
        or expectations is None
    ):
        raise V31CycleAuthoringError("V31_AUTHORING_OPEN_ANALYSIS_SPEC_INVALID")
    cloud = _probability_cloud_spec(probability_cloud_spec)
    scenario = _scenario_spec(scenario_path_set_spec)
    actions = _action_specs(action_candidate_specs)
    novelty = (
        dict(sorted(hypothesis_novelty_rationales.items()))
        if isinstance(hypothesis_novelty_rationales, Mapping)
        and hypothesis_novelty_rationales
        and all(
            isinstance(key, str)
            and key.strip()
            and isinstance(value, str)
            and value.strip()
            for key, value in hypothesis_novelty_rationales.items()
        )
        else None
    )
    if novelty is None:
        raise V31CycleAuthoringError("V31_AUTHORING_NOVELTY_INVALID")
    semantic_payload = {
        "information_interpretations": list(information_interpretations),
        "operational_synthesis": operational_synthesis,
        "sentiment_axis_analyses": list(sentiment_axis_analyses),
        "graph_delta_spec": graph,
        "hypothesis_deltas": hypotheses,
        "expectation_deltas": expectations,
        "probability_cloud_spec": cloud,
        "scenario_path_set_spec": scenario,
        "action_candidate_specs": actions,
        "competing_explanations": list(competing_explanations),
        "unknowns": list(unknowns),
        "requested_observations": list(requested_observations),
        "hypothesis_novelty_rationales": novelty,
        "limitations": list(limitations),
    }
    if _contains_key(semantic_payload, _FORBIDDEN_SELECTION_KEYS):
        raise V31CycleAuthoringError("V31_AUTHORING_SELECTION_FIELD_FORBIDDEN")
    if _contains_key(semantic_payload, _FORBIDDEN_NUMERIC_PROBABILITY_KEYS):
        raise V31CycleAuthoringError(
            "V31_AUTHORING_NUMERIC_PROBABILITY_FIELD_FORBIDDEN"
        )
    return self_digest(
        {
            "schema_id": AUTHORING_ENVELOPE_SCHEMA_ID,
            "schema_version": "1.1.0",
            "run_id": authoring_packet["run_id"],
            "cycle_index": authoring_packet["cycle_index"],
            "decision_at": authoring_packet["decision_at"],
            "symbol": authoring_packet["symbol"],
            AUTHORING_PACKET_DIGEST_FIELD: packet_digest,
            "semantic_specification_version": (
                "V31_PRODUCTION_SEMANTIC_COMPILER_INPUT_1_0_0"
            ),
            "information_interpretations": _strings(
                information_interpretations,
                "V31_AUTHORING_INTERPRETATIONS_INVALID",
                sort=True,
            ),
            "operational_synthesis": _text(
                operational_synthesis,
                "V31_AUTHORING_OPERATIONAL_SYNTHESIS_INVALID",
            ),
            "sentiment_axis_analyses": _sentiment_rows(sentiment_axis_analyses),
            "graph_delta_spec": graph,
            "hypothesis_deltas": hypotheses,
            "expectation_deltas": expectations,
            "probability_cloud_spec": cloud,
            "scenario_path_set_spec": scenario,
            "action_candidate_specs": actions,
            "competing_explanations": _strings(
                competing_explanations,
                "V31_AUTHORING_COMPETING_EXPLANATIONS_INVALID",
                sort=True,
            ),
            "unknowns": _strings(
                unknowns, "V31_AUTHORING_UNKNOWNS_INVALID", sort=True
            ),
            "requested_observations": _strings(
                requested_observations,
                "V31_AUTHORING_REQUESTED_OBSERVATIONS_INVALID",
                sort=True,
            ),
            "hypothesis_novelty_rationales": novelty,
            "limitations": _strings(
                limitations, "V31_AUTHORING_LIMITATIONS_INVALID", sort=True
            ),
            "proposal_phase": "OPEN_ANALYSIS_ONLY_REQUIRES_APPLICATION_COMPILATION",
            "probability_representation": (
                "ORDINAL_PLAUSIBILITY_WITH_OTHER_UNKNOWN_NO_NUMERIC_PROBABILITY"
            ),
            "selection_fields_admitted": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        AUTHORING_ENVELOPE_DIGEST_FIELD,
    )


def validate_v31_agent_open_analysis_envelope(
    document: Mapping[str, Any], *, authoring_packet: Mapping[str, Any]
) -> str:
    digest = _verify_self(
        document,
        AUTHORING_ENVELOPE_DIGEST_FIELD,
        "V31_AUTHORING_ENVELOPE_DIGEST_INVALID",
    )
    if not isinstance(document, Mapping) or set(document) != _ENVELOPE_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_ENVELOPE_SCHEMA_INVALID")
    rebuilt = seal_v31_agent_open_analysis_envelope(
        authoring_packet=authoring_packet,
        information_interpretations=document["information_interpretations"],
        operational_synthesis=document["operational_synthesis"],
        sentiment_axis_analyses=document["sentiment_axis_analyses"],
        graph_delta_spec=document["graph_delta_spec"],
        hypothesis_deltas=document["hypothesis_deltas"],
        expectation_deltas=document["expectation_deltas"],
        probability_cloud_spec=document["probability_cloud_spec"],
        scenario_path_set_spec=document["scenario_path_set_spec"],
        action_candidate_specs=document["action_candidate_specs"],
        competing_explanations=document["competing_explanations"],
        unknowns=document["unknowns"],
        requested_observations=document["requested_observations"],
        hypothesis_novelty_rationales=document[
            "hypothesis_novelty_rationales"
        ],
        limitations=document["limitations"],
    )
    if rebuilt != dict(document) or digest != rebuilt[AUTHORING_ENVELOPE_DIGEST_FIELD]:
        raise V31CycleAuthoringError("V31_AUTHORING_ENVELOPE_NOT_CANONICAL")
    return digest


def seal_v31_authoring_compilation_receipt(
    *,
    authoring_packet: Mapping[str, Any],
    authoring_envelope: Mapping[str, Any],
    inputs_receipt_digest: str,
    agent_proposal_digest: str,
    action_evaluation_digest: str,
    preselection_digest: str,
    compiler_id: str,
    compiled_at: str,
) -> dict[str, Any]:
    packet_digest = validate_v31_proposal_authoring_packet(authoring_packet)
    envelope_digest = validate_v31_agent_open_analysis_envelope(
        authoring_envelope, authoring_packet=authoring_packet
    )
    return self_digest(
        {
            "schema_id": AUTHORING_COMPILATION_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": authoring_packet["run_id"],
            "cycle_index": authoring_packet["cycle_index"],
            "compiled_at": _timestamp(
                compiled_at, "V31_AUTHORING_COMPILED_AT_INVALID"
            ),
            AUTHORING_PACKET_DIGEST_FIELD: packet_digest,
            AUTHORING_ENVELOPE_DIGEST_FIELD: envelope_digest,
            "inputs_receipt_digest": _digest(
                inputs_receipt_digest, "V31_AUTHORING_COMPILED_DIGEST_INVALID"
            ),
            "agent_proposal_digest": _digest(
                agent_proposal_digest, "V31_AUTHORING_COMPILED_DIGEST_INVALID"
            ),
            "action_evaluation_digest": _digest(
                action_evaluation_digest, "V31_AUTHORING_COMPILED_DIGEST_INVALID"
            ),
            "preselection_digest": _digest(
                preselection_digest, "V31_AUTHORING_COMPILED_DIGEST_INVALID"
            ),
            "compiler_id": _text(
                compiler_id, "V31_AUTHORING_COMPILER_ID_INVALID"
            ),
            "deterministic_replay_passed": True,
            "selection_fields_admitted": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        AUTHORING_COMPILATION_DIGEST_FIELD,
    )


def validate_v31_authoring_compilation_receipt(
    document: Mapping[str, Any],
    *,
    authoring_packet: Mapping[str, Any],
    authoring_envelope: Mapping[str, Any],
) -> str:
    digest = _verify_self(
        document,
        AUTHORING_COMPILATION_DIGEST_FIELD,
        "V31_AUTHORING_COMPILATION_DIGEST_INVALID",
    )
    if not isinstance(document, Mapping) or set(document) != _COMPILATION_FIELDS:
        raise V31CycleAuthoringError("V31_AUTHORING_COMPILATION_SCHEMA_INVALID")
    rebuilt = seal_v31_authoring_compilation_receipt(
        authoring_packet=authoring_packet,
        authoring_envelope=authoring_envelope,
        inputs_receipt_digest=document["inputs_receipt_digest"],
        agent_proposal_digest=document["agent_proposal_digest"],
        action_evaluation_digest=document["action_evaluation_digest"],
        preselection_digest=document["preselection_digest"],
        compiler_id=document["compiler_id"],
        compiled_at=document["compiled_at"],
    )
    if rebuilt != dict(document) or digest != rebuilt[AUTHORING_COMPILATION_DIGEST_FIELD]:
        raise V31CycleAuthoringError("V31_AUTHORING_COMPILATION_NOT_CANONICAL")
    return digest


def seal_v31_authoring_compilation_admission(
    *,
    run_id: str,
    cycle_index: int,
    admitted_at: str,
    compiler_id: str,
    authoring_packet_binding: Mapping[str, Any],
    proposal_attempt_binding: Mapping[str, Any],
    proposal_request_binding: Mapping[str, Any],
    proposal_claim_binding: Mapping[str, Any],
    proposal_delivery_binding: Mapping[str, Any],
    proposal_consume_binding: Mapping[str, Any],
    inputs_receipt_binding: Mapping[str, Any],
    agent_proposal_binding: Mapping[str, Any],
    action_evaluation_binding: Mapping[str, Any],
    preselection_binding: Mapping[str, Any],
    compilation_receipt_binding: Mapping[str, Any],
    compiled_assembly_bundle_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind durable authoring, compilation replay, and preselection artifacts.

    This admission only unblocks the postseal selection request.  It is not a
    selection, experiment-start receipt, or execution authority.
    """

    return self_digest(
        {
            "schema_id": AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID,
            "schema_version": "1.0.0",
            "run_id": _text(run_id, "V31_AUTHORING_ADMISSION_RUN_ID_INVALID"),
            "cycle_index": _cycle(cycle_index),
            "admitted_at": _timestamp(
                admitted_at, "V31_AUTHORING_ADMISSION_TIME_INVALID"
            ),
            "compiler_id": _text(
                compiler_id, "V31_AUTHORING_ADMISSION_COMPILER_ID_INVALID"
            ),
            "authoring_packet_binding": validate_v31_authoring_binding(
                authoring_packet_binding,
                expected_schema_id=AUTHORING_PACKET_SCHEMA_ID,
                expected_digest_field=AUTHORING_PACKET_DIGEST_FIELD,
            ),
            "proposal_attempt_binding": validate_v31_authoring_binding(
                proposal_attempt_binding,
                expected_schema_id="theory_paper_v31_agent_attempt",
                expected_digest_field="attempt_digest",
            ),
            "proposal_request_binding": validate_v31_authoring_binding(
                proposal_request_binding,
                expected_schema_id="theory_paper_v31_agent_request",
                expected_digest_field="request_digest",
            ),
            "proposal_claim_binding": validate_v31_authoring_binding(
                proposal_claim_binding,
                expected_schema_id="theory_paper_v31_agent_claim",
                expected_digest_field="claim_digest",
            ),
            "proposal_delivery_binding": validate_v31_authoring_binding(
                proposal_delivery_binding,
                expected_schema_id="theory_paper_v31_agent_delivery",
                expected_digest_field="delivery_digest",
            ),
            "proposal_consume_binding": validate_v31_authoring_binding(
                proposal_consume_binding,
                expected_schema_id="theory_paper_v31_agent_consume_receipt",
                expected_digest_field="consume_digest",
            ),
            "inputs_receipt_binding": validate_v31_authoring_binding(
                inputs_receipt_binding,
                expected_schema_id="theory_paper_v2_v31_inputs_receipt",
                expected_digest_field="inputs_receipt_digest",
            ),
            "agent_proposal_binding": validate_v31_authoring_binding(
                agent_proposal_binding,
                expected_schema_id="theory_paper_v2_v31_agent_proposal",
                expected_digest_field="agent_proposal_digest",
            ),
            "action_evaluation_binding": validate_v31_authoring_binding(
                action_evaluation_binding,
                expected_schema_id=(
                    "theory_paper_v2_v31_complete_action_evaluation"
                ),
                expected_digest_field="action_evaluation_digest",
            ),
            "preselection_binding": validate_v31_authoring_binding(
                preselection_binding,
                expected_schema_id="theory_paper_v2_v31_cycle_preselection",
                expected_digest_field="preselection_digest",
            ),
            "compilation_receipt_binding": validate_v31_authoring_binding(
                compilation_receipt_binding,
                expected_schema_id=AUTHORING_COMPILATION_SCHEMA_ID,
                expected_digest_field=AUTHORING_COMPILATION_DIGEST_FIELD,
            ),
            "compiled_assembly_bundle_binding": validate_v31_authoring_binding(
                compiled_assembly_bundle_binding,
                expected_schema_id=COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID,
                expected_digest_field=COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD,
            ),
            "deterministic_replay_passed": True,
            "selection_unblocked": True,
            "selection_performed": False,
            "chat_history_is_authority": False,
            "external_execution_authority": "NONE_LOCAL_SIMULATION",
            "executable": False,
        },
        AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
    )


def validate_v31_authoring_compilation_admission(
    document: Mapping[str, Any],
) -> str:
    digest = _verify_self(
        document,
        AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD,
        "V31_AUTHORING_ADMISSION_DIGEST_INVALID",
    )
    if (
        not isinstance(document, Mapping)
        or set(document) != _COMPILATION_ADMISSION_FIELDS
        or document.get("schema_id")
        != AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID
        or document.get("schema_version") != "1.0.0"
    ):
        raise V31CycleAuthoringError(
            "V31_AUTHORING_ADMISSION_SCHEMA_INVALID"
        )
    rebuilt = seal_v31_authoring_compilation_admission(
        run_id=document["run_id"],
        cycle_index=document["cycle_index"],
        admitted_at=document["admitted_at"],
        compiler_id=document["compiler_id"],
        authoring_packet_binding=document["authoring_packet_binding"],
        proposal_attempt_binding=document["proposal_attempt_binding"],
        proposal_request_binding=document["proposal_request_binding"],
        proposal_claim_binding=document["proposal_claim_binding"],
        proposal_delivery_binding=document["proposal_delivery_binding"],
        proposal_consume_binding=document["proposal_consume_binding"],
        inputs_receipt_binding=document["inputs_receipt_binding"],
        agent_proposal_binding=document["agent_proposal_binding"],
        action_evaluation_binding=document["action_evaluation_binding"],
        preselection_binding=document["preselection_binding"],
        compilation_receipt_binding=document["compilation_receipt_binding"],
        compiled_assembly_bundle_binding=document[
            "compiled_assembly_bundle_binding"
        ],
    )
    if rebuilt != dict(document) or digest != rebuilt[
        AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD
    ]:
        raise V31CycleAuthoringError(
            "V31_AUTHORING_ADMISSION_NOT_CANONICAL"
        )
    return digest


__all__ = [
    "AUTHORING_COMPILATION_ADMISSION_DIGEST_FIELD",
    "AUTHORING_COMPILATION_ADMISSION_SCHEMA_ID",
    "AUTHORING_COMPILATION_DIGEST_FIELD",
    "COMPILED_ASSEMBLY_BUNDLE_DIGEST_FIELD",
    "COMPILED_ASSEMBLY_BUNDLE_SCHEMA_ID",
    "AUTHORING_COMPILATION_SCHEMA_ID",
    "AUTHORING_ENVELOPE_DIGEST_FIELD",
    "AUTHORING_ENVELOPE_SCHEMA_ID",
    "AUTHORING_PACKET_DIGEST_FIELD",
    "AUTHORING_PACKET_SCHEMA_ID",
    "V31CycleAuthoringError",
    "seal_v31_agent_open_analysis_envelope",
    "seal_v31_authoring_compilation_admission",
    "seal_v31_authoring_compilation_receipt",
    "seal_v31_proposal_authoring_packet",
    "validate_v31_agent_open_analysis_envelope",
    "validate_v31_authoring_compilation_admission",
    "validate_v31_authoring_binding",
    "validate_v31_authoring_compilation_receipt",
    "validate_v31_proposal_authoring_packet",
]
