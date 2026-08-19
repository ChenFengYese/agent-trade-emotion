"""Frozen-input construction, deterministic scoring and resumable E0 batch.

The module composes the generative topology runner with a deterministic
strategic-state and portfolio reducer.  It does not grant paper/live authority.
All model prose is evidence only; only an exact feasible ``selected_action``
identifier can reach the state reducer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .formal_experiment import (
    PairedObservationReceipt,
    build_paired_observation_receipt,
)
from .generative_topology_run import (
    FORMAL_TOPOLOGY_IDS,
    FrozenInstruction,
    GenerativeModelPort,
    GenerativeTopologyRunError,
    PairedGenerativeRunRequest,
    ProjectionValue,
    ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA,
    RunEvidenceClass,
    make_deterministic_object_ref,
    run_paired_generative_topologies,
    validate_formal_experiment_contract,
)
from .topology_evaluation import evaluate_agent_topologies
from ..domain.contracts.canonical import (
    canonical_bytes,
    canonical_digest,
    load_json_strict,
    loads_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.formal_e0_replay import (
    FormalE0ReplayError,
    FrozenAccountPolicy,
    ReplayTransition,
    StrategicEpisodeState,
    account_policy_from_documents,
    feasible_action_documents,
    frozen_reference_action,
    initial_episode_state,
    preview_action,
    replay_action_one_hour,
)
from ..infrastructure.formal_e0_batch_store import (
    PreparedFormalE0Run,
    load_prepared_formal_e0_run,
    write_resume_json,
)
from ..infrastructure.formal_experiment_store import (
    load_paired_observation_receipt,
)
from ..infrastructure.generative_topology.archive import (
    PairedRunArchiveError,
    WriteOncePairedRunArchive,
)


CHALLENGE_CATEGORIES = (
    "STATE_CONTINUITY",
    "TIME_SCALE_OVERREACH",
    "EXIT_REENTRY_ASYMMETRY",
    "UNKNOWN_COERCION",
    "ACTION_SPACE_COLLAPSE",
    "ROLE_OVERREACH",
)
COHORT_RANGES = {
    "TOPOLOGY_SELECTION": range(96, 128),
    "POLICY_QUALIFICATION": range(128, 160),
    "FORMAL_EXPERIMENT": range(160, 192),
}
COHORT_CODES = {
    "TOPOLOGY_SELECTION": "selection",
    "POLICY_QUALIFICATION": "qualification",
    "FORMAL_EXPERIMENT": "formal",
}
ROLE_VISIBLE_1H_WINDOW_BARS = 96
_VISIBLE_1H_FIELDS = (
    "bar_id",
    "available_at",
    "open_time_ms",
    "close_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_asset_volume",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "trade_count",
    "availability_status",
    "decision_contemporaneous_status",
)
_DERIVED_BAR_FIELDS = (
    "derived_bar_id",
    "available_at",
    "open_time_ms",
    "close_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "derivation_status",
)


class FormalE0BatchError(ValueError):
    """A formal batch admission, replay, or resume failure."""


@dataclass(frozen=True, slots=True)
class FrozenDatasetView:
    dataset: Mapping[str, Any]
    bars: tuple[Mapping[str, Any], ...]
    decision_slots_by_sample: Mapping[int, Mapping[str, Any]]
    derived_4h: tuple[Mapping[str, Any], ...]
    derived_1d: tuple[Mapping[str, Any], ...]

    def current_bar(self, sample_index: int) -> Mapping[str, Any]:
        try:
            return self.bars[sample_index]
        except IndexError as exc:
            raise FormalE0BatchError("SAMPLE_INDEX_OUTSIDE_DATASET") from exc

    def next_bar(self, sample_index: int) -> Mapping[str, Any]:
        try:
            return self.bars[sample_index + 1]
        except IndexError as exc:
            raise FormalE0BatchError("OUTCOME_BAR_MISSING") from exc

    def decision_slot(self, sample_index: int) -> Mapping[str, Any]:
        try:
            return self.decision_slots_by_sample[sample_index]
        except KeyError as exc:
            raise FormalE0BatchError("DECISION_SLOT_MISSING") from exc


@dataclass(frozen=True, slots=True)
class DecisionInputPackage:
    sample_index: int
    cohort: str
    context_document: Mapping[str, Any]
    decision_context_ref: Mapping[str, Any]
    projections: tuple[ProjectionValue, ...]
    state: StrategicEpisodeState
    current_bar: Mapping[str, Any]
    next_bar: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DeterministicArmScore:
    topology_id: str
    semantic_outputs: tuple[Mapping[str, Any], ...]
    selected_action_id: str | None
    dynamic_candidate_coverage: Decimal
    material_challenge_coverage: Decimal
    action_quality_score: Decimal
    action_quality_components: Mapping[str, bool]
    candidate_components: Mapping[str, bool]
    discovered_challenge_categories: tuple[str, ...]
    safety_state_pit_authority_failures: int
    role_overreach_failures: int
    hard_constraint_error_count: int
    state_continuity_error_count: int
    reproducibility_difference_count: int
    qualification_verdict: str
    calculation_digest: str


@dataclass(frozen=True, slots=True)
class SampleCompletion:
    observation: PairedObservationReceipt
    decision_receipt: Mapping[str, Any]
    state_after: StrategicEpisodeState
    baseline_state_after: StrategicEpisodeState | None


def _load_dataset(prepared: PreparedFormalE0Run) -> FrozenDatasetView:
    dataset = load_json_strict(prepared.dataset_path)
    if (
        dataset.get("dataset_type") != "HISTORICAL_COUNTERFACTUAL_REPLAY"
        or dataset.get("experiment_contract_digest")
        != validate_formal_experiment_contract(
            load_json_strict(prepared.formal_contract_path)
        )
        or dataset.get("decision_indices_inclusive") != [96, 191]
        or dataset.get("outcome_horizons_hours") != [1, 4, 8, 24]
        or dataset.get("forming_or_future_rows_excluded") != 0
        or dataset.get("executable") is not False
    ):
        raise FormalE0BatchError("FROZEN_DATASET_CONTRACT_MISMATCH")
    bars_raw = dataset.get("bars")
    slots_raw = dataset.get("decision_slots")
    if (
        not isinstance(bars_raw, list)
        or len(bars_raw) != 256
        or not isinstance(slots_raw, list)
        or len(slots_raw) != 96
    ):
        raise FormalE0BatchError("FROZEN_DATASET_SHAPE_INVALID")
    bars = tuple(
        item
        for item in bars_raw
        if isinstance(item, Mapping)
    )
    if len(bars) != 256:
        raise FormalE0BatchError("FROZEN_BAR_SHAPE_INVALID")
    slots: dict[int, Mapping[str, Any]] = {}
    for offset, item in enumerate(slots_raw):
        if not isinstance(item, Mapping) or item.get("slot_index") != offset:
            raise FormalE0BatchError("DECISION_SLOT_INDEX_INVALID")
        slots[offset + 96] = item
    derived_4h = tuple(
        item
        for item in dataset.get("derived_4h_bars", [])
        if isinstance(item, Mapping)
    )
    derived_1d = tuple(
        item
        for item in dataset.get("derived_1d_bars", [])
        if isinstance(item, Mapping)
    )
    return FrozenDatasetView(
        dataset=dataset,
        bars=bars,
        decision_slots_by_sample=slots,
        derived_4h=derived_4h,
        derived_1d=derived_1d,
    )


def _field_row(
    item: Mapping[str, Any], fields: Sequence[str], *, error_code: str
) -> list[Any]:
    if any(key not in item for key in fields):
        raise FormalE0BatchError(error_code)
    return [item[key] for key in fields]


def _field_rows_document(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    *,
    error_code: str,
) -> dict[str, Any]:
    """Encode losslessly while emitting field names only once."""

    return {
        "encoding": "ORDERED_FIELDS_AND_ROWS_V1",
        "fields": list(fields),
        "rows": [
            _field_row(item, fields, error_code=error_code)
            for item in rows
        ],
        "row_count": len(rows),
    }


def _compact_visible_bars(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(rows) > ROLE_VISIBLE_1H_WINDOW_BARS:
        raise FormalE0BatchError("VISIBLE_BAR_WINDOW_LIMIT_EXCEEDED")
    if not rows:
        raise FormalE0BatchError("VISIBLE_BAR_REQUIRED_FIELD_MISSING")
    return _field_rows_document(
        rows,
        _VISIBLE_1H_FIELDS,
        error_code="VISIBLE_BAR_REQUIRED_FIELD_MISSING",
    )


def _derived_visible(
    rows: Sequence[Mapping[str, Any]], decision_at: str
) -> dict[str, Any]:
    visible = [
        item
        for item in rows
        if str(item.get("available_at", "")) <= decision_at
    ]
    return _field_rows_document(
        visible,
        _DERIVED_BAR_FIELDS,
        error_code="DERIVED_BAR_REQUIRED_FIELD_MISSING",
    )


def _risk_budget(
    state: StrategicEpisodeState,
    *,
    mark: Decimal,
    account: FrozenAccountPolicy,
) -> dict[str, Any]:
    used = (
        Decimal(0)
        if state.quantity == 0 or state.hard_stop is None
        else state.quantity
        * max(Decimal(0), mark - state.hard_stop)
        / account.initial_equity
    )
    maximum = account.max_gross_fraction * account.hard_stop_fraction
    return {
        "risk_unit": "FRACTION_OF_INITIAL_EQUITY",
        "maximum_open_risk_fraction": maximum,
        "used_open_risk_fraction": used,
        "remaining_open_risk_fraction": max(Decimal(0), maximum - used),
        "nominal_gross_fraction": state.nominal_gross_fraction,
        "max_gross_fraction": account.max_gross_fraction,
        "core_fraction": account.core_fraction,
        "stage_fraction": account.stage_fraction,
        "hard_stop_fraction": account.hard_stop_fraction,
        "funding": None,
        "funding_status": "UNKNOWN_EXCLUDED",
    }


_CONTINUITY_FIELDS = {
    "schema_id",
    "schema_version",
    "continuity_kind",
    "cohort",
    "expected_sample_index",
    "previous_sample_index",
    "previous_decision_receipt_ref",
    "previous_decision_context_ref",
    "accepted_selector_semantic_payload",
    "calculation_summary",
    "governance_summary",
    "previous_selected_action_id",
    "previous_transition_head",
    "state_digest_at_handoff",
    "prior_accepted_head",
    "analysis_evidence_authority",
    "system_mode",
    "external_execution_authority",
    "executable",
    "continuity_digest",
}


def _continuity_document(
    *,
    kind: str,
    state: StrategicEpisodeState,
    expected_sample_index: int,
    previous_sample_index: int | None,
    previous_decision_receipt_ref: Mapping[str, Any] | None,
    previous_decision_context_ref: Mapping[str, Any] | None,
    accepted_selector_semantic_payload: Mapping[str, Any] | None,
    calculation_summary: Mapping[str, Any] | None,
    governance_summary: Mapping[str, Any] | None,
    previous_selected_action_id: str | None,
    previous_transition_head: str | None,
) -> dict[str, Any]:
    return self_digest(
        {
            "schema_id": "formal_e0_prior_accepted_analysis",
            "schema_version": "1.0.0",
            "continuity_kind": kind,
            "cohort": state.cohort,
            "expected_sample_index": expected_sample_index,
            "previous_sample_index": previous_sample_index,
            "previous_decision_receipt_ref": (
                dict(previous_decision_receipt_ref)
                if previous_decision_receipt_ref is not None
                else None
            ),
            "previous_decision_context_ref": (
                dict(previous_decision_context_ref)
                if previous_decision_context_ref is not None
                else None
            ),
            "accepted_selector_semantic_payload": (
                dict(accepted_selector_semantic_payload)
                if accepted_selector_semantic_payload is not None
                else None
            ),
            "calculation_summary": (
                dict(calculation_summary)
                if calculation_summary is not None
                else None
            ),
            "governance_summary": (
                dict(governance_summary)
                if governance_summary is not None
                else None
            ),
            "previous_selected_action_id": previous_selected_action_id,
            "previous_transition_head": previous_transition_head,
            "state_digest_at_handoff": state.document()["state_digest"],
            "prior_accepted_head": state.prior_accepted_head,
            "analysis_evidence_authority": (
                "NEXT_ROUND_REVIEW_EVIDENCE_ONLY;"
                "NO_MARKET_FACT_ORDER_OR_STATE_MUTATION_AUTHORITY"
            ),
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "continuity_digest",
    )


def _genesis_continuity_evidence(
    state: StrategicEpisodeState, sample_index: int
) -> dict[str, Any]:
    return _continuity_document(
        kind="GENESIS",
        state=state,
        expected_sample_index=sample_index,
        previous_sample_index=None,
        previous_decision_receipt_ref=None,
        previous_decision_context_ref=None,
        accepted_selector_semantic_payload=None,
        calculation_summary=None,
        governance_summary={"status": "GENESIS_NO_PRIOR_ACCEPTED_ANALYSIS"},
        previous_selected_action_id=None,
        previous_transition_head=None,
    )


def _selection_reference_continuity_evidence(
    *,
    prepared: PreparedFormalE0Run,
    transition: ReplayTransition,
    expected_sample_index: int,
) -> dict[str, Any]:
    receipt = transition.receipt()
    return _continuity_document(
        kind="PRE_FROZEN_SELECTION_REFERENCE",
        state=transition.state_after,
        expected_sample_index=expected_sample_index,
        previous_sample_index=transition.state_after.last_sample_index,
        previous_decision_receipt_ref={
            "artifact_kind": "PRE_FROZEN_SELECTION_REFERENCE_TRANSITION",
            "run_bindings_digest": prepared.run_bindings_digest,
            "receipt_digest": receipt["receipt_digest"],
        },
        previous_decision_context_ref=None,
        accepted_selector_semantic_payload=None,
        calculation_summary={
            "status": "NOT_APPLICABLE_PAIRED_REFERENCE_CONTROL"
        },
        governance_summary={
            "state_application_mode": "PAIRED_REFERENCE_CONTROL",
            "executed_action_id": transition.executed_action_id,
            "natural_language_state_authority": "NONE",
        },
        previous_selected_action_id=transition.executed_action_id,
        previous_transition_head=transition.transition_head_digest,
    )


def _validate_continuity_evidence(
    evidence: Mapping[str, Any],
    *,
    state: StrategicEpisodeState,
    sample_index: int,
) -> None:
    if set(evidence) != _CONTINUITY_FIELDS:
        raise FormalE0BatchError("PRIOR_ANALYSIS_FIELD_SET_INVALID")
    verify_self_digest(evidence, "continuity_digest")
    if (
        evidence.get("schema_id") != "formal_e0_prior_accepted_analysis"
        or evidence.get("schema_version") != "1.0.0"
        or evidence.get("cohort") != state.cohort
        or evidence.get("expected_sample_index") != sample_index
        or evidence.get("state_digest_at_handoff")
        != state.document()["state_digest"]
        or evidence.get("prior_accepted_head")
        != state.prior_accepted_head
        or evidence.get("analysis_evidence_authority")
        != (
            "NEXT_ROUND_REVIEW_EVIDENCE_ONLY;"
            "NO_MARKET_FACT_ORDER_OR_STATE_MUTATION_AUTHORITY"
        )
        or evidence.get("system_mode") != "E0_OFFLINE_COUNTERFACTUAL"
        or evidence.get("external_execution_authority") != "NONE_E0"
        or evidence.get("executable") is not False
    ):
        raise FormalE0BatchError("PRIOR_ANALYSIS_HANDOFF_INVALID")
    kind = evidence.get("continuity_kind")
    if state.last_sample_index is None:
        if (
            sample_index != COHORT_RANGES[state.cohort].start
            or kind != "GENESIS"
            or evidence.get("previous_sample_index") is not None
            or evidence.get("previous_transition_head") is not None
            or evidence.get("accepted_selector_semantic_payload") is not None
            or evidence.get("previous_decision_receipt_ref") is not None
            or evidence.get("previous_decision_context_ref") is not None
            or evidence.get("previous_selected_action_id") is not None
        ):
            raise FormalE0BatchError("PRIOR_ANALYSIS_GENESIS_INVALID")
        return
    if (
        state.last_sample_index != sample_index - 1
        or evidence.get("previous_sample_index") != sample_index - 1
        or evidence.get("previous_transition_head")
        != state.prior_accepted_head
    ):
        raise FormalE0BatchError("PRIOR_ANALYSIS_CHAIN_BROKEN")
    if state.cohort == "TOPOLOGY_SELECTION":
        reference = evidence.get("previous_decision_receipt_ref")
        if (
            kind != "PRE_FROZEN_SELECTION_REFERENCE"
            or evidence.get("accepted_selector_semantic_payload") is not None
            or not isinstance(reference, Mapping)
            or set(reference)
            != {
                "artifact_kind",
                "run_bindings_digest",
                "receipt_digest",
            }
        ):
            raise FormalE0BatchError(
                "SELECTION_REFERENCE_CONTINUITY_INVALID"
            )
    else:
        selector = evidence.get("accepted_selector_semantic_payload")
        receipt_ref = evidence.get("previous_decision_receipt_ref")
        context_ref = evidence.get("previous_decision_context_ref")
        if (
            kind != "ACCEPTED_SELECTOR_DECISION"
            or not isinstance(selector, Mapping)
            or selector.get("output_kind") != "SELECTION"
            or selector.get("selected_action")
            != evidence.get("previous_selected_action_id")
            or not isinstance(evidence.get("calculation_summary"), Mapping)
            or not isinstance(evidence.get("governance_summary"), Mapping)
            or not isinstance(receipt_ref, Mapping)
            or set(receipt_ref)
            != {
                "artifact_kind",
                "relative_path",
                "receipt_digest",
                "physical_sha256",
            }
            or not isinstance(context_ref, Mapping)
            or set(context_ref)
            != {
                "artifact_kind",
                "relative_path",
                "context_digest",
                "physical_sha256",
            }
        ):
            raise FormalE0BatchError(
                "ACCEPTED_SELECTOR_CONTINUITY_INVALID"
            )


def build_decision_input_package(
    *,
    prepared: PreparedFormalE0Run,
    dataset: FrozenDatasetView,
    state: StrategicEpisodeState,
    sample_index: int,
    account: FrozenAccountPolicy,
    continuity_evidence: Mapping[str, Any] | None = None,
) -> DecisionInputPackage:
    """Build one no-future common context bound to the decision slot."""

    cohort = state.cohort
    expected = COHORT_RANGES.get(cohort)
    if expected is None or sample_index not in expected:
        raise FormalE0BatchError("STATE_COHORT_SAMPLE_INDEX_MISMATCH")
    if continuity_evidence is None:
        continuity_evidence = _genesis_continuity_evidence(
            state, sample_index
        )
    _validate_continuity_evidence(
        continuity_evidence,
        state=state,
        sample_index=sample_index,
    )
    slot = dataset.decision_slot(sample_index)
    current = dataset.current_bar(sample_index)
    next_bar = dataset.next_bar(sample_index)
    decision_at = str(slot.get("decision_at"))
    expected_ids = [str(item["bar_id"]) for item in dataset.bars[: sample_index + 1]]
    visible_ids = slot.get("visible_bar_ids")
    if (
        visible_ids != expected_ids
        or slot.get("visible_through_bar_id") != current.get("bar_id")
        or current.get("available_at") != decision_at
    ):
        raise FormalE0BatchError("DECISION_SLOT_VISIBLE_BAR_BINDING_INVALID")
    fully_visible = dataset.bars[: sample_index + 1]
    future_count = sum(
        str(item["available_at"]) > decision_at for item in fully_visible
    )
    if future_count:
        raise FormalE0BatchError("FUTURE_BAR_IN_ROLE_INPUT")
    projected_source = fully_visible[-ROLE_VISIBLE_1H_WINDOW_BARS:]
    omitted_visible_count = len(fully_visible) - len(projected_source)
    visible = _compact_visible_bars(projected_source)
    unknowns = [
        {
            "field_name": item["field_name"],
            "status": item["status"],
            "value": None,
            "reason_code": item["reason_code"],
            "unit": item["unit"],
        }
        for item in slot.get("interface_fields", [])
        if isinstance(item, Mapping) and item.get("status") == "UNKNOWN"
    ]
    if any(item["value"] is not None for item in unknowns):
        raise FormalE0BatchError("TYPED_UNKNOWN_COERCED")
    mark = Decimal(str(current["close"]))
    feasible = feasible_action_documents(
        state, current_mark=mark, account=account
    )
    context = self_digest(
        {
            "schema_id": "formal_e0_decision_context",
            "schema_version": "1.1.0",
            "decision_context_id": (
                f"{prepared.run_id}:{COHORT_CODES[cohort]}:{sample_index:03d}"
            ),
            "formal_contract_digest": validate_formal_experiment_contract(
                load_json_strict(prepared.formal_contract_path)
            ),
            "dataset_manifest_digest": (
                prepared.dataset_manifest_digest
            ),
            "dataset_payload_digest": prepared.dataset_payload_digest,
            "sample_index": sample_index,
            "sample_cohort": cohort,
            "decision_at": decision_at,
            "decision_slot_id": slot["slot_id"],
            "decision_slot_digest": slot["slot_digest"],
            "market": {
                "provider_id": dataset.dataset["provider_id"],
                "symbol": dataset.dataset["symbol"],
                "interval": dataset.dataset["interval"],
                "visible_bars": visible,
                "visible_4h_bars": _derived_visible(
                    dataset.derived_4h, decision_at
                ),
                "visible_1d_bars": _derived_visible(
                    dataset.derived_1d, decision_at
                ),
                "source_metadata_authority": (
                    "FROZEN_DATASET_AND_DECISION_SLOT_REFERENCES;"
                    "NOT_REPEATED_PER_BAR"
                ),
            },
            "strategic_episode_state": state.document(),
            "prior_accepted_head": state.prior_accepted_head,
            "prior_accepted_analysis": dict(continuity_evidence),
            "typed_unknowns": unknowns,
            "risk_budget": _risk_budget(
                state, mark=mark, account=account
            ),
            "feasible_actions": list(feasible),
            "pit_authority": {
                "slot_full_history_binding_verified": True,
                "slot_visible_bar_count": len(fully_visible),
                "projected_1h_bar_count": len(projected_source),
                "projection_window_limit_bars": (
                    ROLE_VISIBLE_1H_WINDOW_BARS
                ),
                "earlier_visible_not_projected_count": (
                    omitted_visible_count
                ),
                "earlier_visible_not_projected_reason": (
                    "FROZEN_ROLLING_WARMUP_LIMIT_96_BARS"
                    if omitted_visible_count
                    else None
                ),
                "future_visibility_count": future_count,
                "role_visible_from_bar_id": projected_source[0]["bar_id"],
                "role_visible_through_bar_id": current["bar_id"],
                "next_outcome_bar_id": None,
                "future_outcome_values_in_role_input": False,
                "physical_capture_status": "CAPTURED_NOW",
                "historical_decision_input_status": "UNKNOWN",
                "usage_scope": "HISTORICAL_COUNTERFACTUAL_REPLAY",
            },
            "state_authority": {
                "natural_language_mutation_authority": "NONE",
                "only_exact_feasible_action_id_can_transition": True,
                "exit_while_thesis_survives_requires_reentry": True,
            },
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "context_digest",
    )
    decision_ref = make_deterministic_object_ref(
        schema_id="formal_e0_decision_context",
        schema_version="1.1.0",
        object_id=str(context["decision_context_id"]),
        payload={
            key: value
            for key, value in context.items()
            if key != "context_digest"
        },
    )
    # Bind the supplied object reference to the exact self-digest document.
    decision_ref = {
        **decision_ref,
        "payload_digest": str(context["context_digest"]),
        "object_digest": str(context["context_digest"]),
    }
    projection_fields = (
        "market",
        "strategic_episode_state",
        "prior_accepted_head",
        "prior_accepted_analysis",
        "typed_unknowns",
        "risk_budget",
        "feasible_actions",
        "pit_authority",
        "state_authority",
        "sample_index",
        "sample_cohort",
        "decision_at",
    )
    projections = tuple(
        ProjectionValue(
            source_object_ref=decision_ref,
            json_pointer=f"/{field}",
            value=context[field],
        )
        for field in projection_fields
    )
    return DecisionInputPackage(
        sample_index=sample_index,
        cohort=cohort,
        context_document=context,
        decision_context_ref=decision_ref,
        projections=projections,
        state=state,
        current_bar=current,
        next_bar=next_bar,
    )


def _load_instructions(
    prepared: PreparedFormalE0Run,
) -> dict[str, FrozenInstruction]:
    value = load_json_strict(prepared.reasoning_instructions_path)
    verify_self_digest(value, "instruction_set_digest")
    result: dict[str, FrozenInstruction] = {}
    for item in value.get("instructions", []):
        if not isinstance(item, Mapping):
            raise FormalE0BatchError("REASONING_INSTRUCTION_INVALID")
        raw = str(item["instruction_text"]).encode("utf-8")
        result[str(item["instruction_id"])] = FrozenInstruction(
            instruction_id=str(item["instruction_id"]),
            instruction_bytes=raw,
            instruction_digest=str(item["instruction_sha256"]),
        )
    return result


def _dataset_object_ref(
    prepared: PreparedFormalE0Run,
) -> dict[str, Any]:
    manifest = load_json_strict(prepared.dataset_manifest_path)
    return {
        "schema_id": str(manifest["schema_id"]),
        "schema_version": str(manifest["schema_version"]),
        "object_id": str(manifest["bundle_id"]),
        "payload_digest": prepared.dataset_manifest_digest,
        "object_digest": prepared.dataset_manifest_digest,
    }


def build_generation_request(
    *,
    prepared: PreparedFormalE0Run,
    package: DecisionInputPackage,
    topology_ids: tuple[str, ...],
    selected_topology_id: str | None,
    topology_selection_result_digest: str | None,
) -> PairedGenerativeRunRequest:
    return PairedGenerativeRunRequest(
        paired_session_id=(
            f"{prepared.run_id}-{COHORT_CODES[package.cohort]}-"
            f"{package.sample_index:03d}"
        ),
        evidence_class=RunEvidenceClass.FORMAL_GENERATIVE,
        dataset_kind="FROZEN_REAL_MARKET",
        sample_cohort=package.cohort,
        sample_index=package.sample_index,
        requested_topology_ids=topology_ids,
        selected_topology_id=selected_topology_id,
        topology_selection_result_digest=(
            topology_selection_result_digest
        ),
        dataset_manifest_ref=_dataset_object_ref(prepared),
        dataset_transport_contract_verdict="PASS",
        dataset_transport_schema_digest=canonical_digest(
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
        ),
        decision_context_ref=package.decision_context_ref,
        common_projection_values=package.projections,
        formal_contract=load_json_strict(prepared.formal_contract_path),
        reasoning_instructions=_load_instructions(prepared),
    )


def assess_formal_transport(
    *,
    prepared: PreparedFormalE0Run,
    model_port: GenerativeModelPort,
) -> dict[str, Any]:
    """Fail closed on requested/served-model or hard-cap uncertainty."""

    capability = model_port.capability()
    contract = load_json_strict(prepared.formal_contract_path)
    reasons = list(capability.reason_codes)
    if not capability.formal_ready(contract):
        reasons.append("GENERATION_TRANSPORT_CONTRACT_NOT_READY")
    if not capability.served_model_attestation_available:
        reasons.append("SERVED_MODEL_ATTESTATION_UNAVAILABLE")
    hard_generation_cap_attested = (
        capability.hard_token_limit_available
        and capability.adapter_id
        == (
            "CODEX_EXEC_GENERATIVE_TRANSPORT:"
            "1.1.0-ROLLOUT-BUDGET-ATTESTED"
        )
    )
    if not hard_generation_cap_attested:
        reasons.append("HARD_GENERATION_LIMIT_UNVERIFIED")
    receipt = self_digest(
        {
            "schema_id": "formal_e0_transport_admission_receipt",
            "schema_version": "1.0.0",
            "run_bindings_digest": prepared.run_bindings_digest,
            "capability": asdict(capability),
            "requested_model": contract["topology_contract"]["model"],
            "served_model_attestation_required": True,
            "hard_generation_limit_mechanism_required": True,
            "hard_generation_limit_adapter_attestation": (
                "CODEX_EXEC_GENERATIVE_TRANSPORT:"
                "1.1.0-ROLLOUT-BUDGET-ATTESTED"
            ),
            "hard_generation_limit_adapter_attested": (
                hard_generation_cap_attested
            ),
            "status": "PASS" if not reasons else "NO_GO",
            "reason_codes": list(dict.fromkeys(reasons)),
            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
            "external_execution_authority": "NONE_E0",
            "executable": False,
        },
        "receipt_digest",
    )
    return receipt


def _semantic_wrapper_path(
    session_root: Path,
    topology_id: str,
    turn_receipt: Mapping[str, Any],
) -> Path:
    ordinal = int(turn_receipt["turn_ordinal"])
    phase = str(turn_receipt["phase_id"]).lower()
    return (
        session_root
        / "arms"
        / topology_id
        / f"turn-{ordinal:02d}-{phase}"
        / "deterministic-wrapper.json"
    )


def _load_semantic_outputs(
    *,
    session_root: Path,
    arm_receipt: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    topology_id = str(arm_receipt["topology_id"])
    outputs = []
    turns = arm_receipt.get("turn_receipts")
    if not isinstance(turns, list) or len(turns) != 3:
        raise FormalE0BatchError("ARM_TURN_SET_INCOMPLETE")
    for turn in turns:
        if not isinstance(turn, Mapping) or turn.get("status") != "COMPLETE":
            raise FormalE0BatchError("ARM_TURN_INCOMPLETE")
        wrapper_path = _semantic_wrapper_path(
            session_root, topology_id, turn
        )
        turn_root = wrapper_path.parent
        physical_paths = (
            (
                turn_root / "provider-input.bin",
                turn.get("provider_input_digest"),
                "PROVIDER_INPUT_PHYSICAL_DIGEST_INVALID",
            ),
            (
                turn_root / "attempt-00" / "raw-events.jsonl",
                turn.get("raw_event_digest"),
                "RAW_EVENT_PHYSICAL_DIGEST_INVALID",
            ),
            (
                turn_root / "attempt-00" / "raw-stderr.bin",
                turn.get("raw_stderr_digest"),
                "RAW_STDERR_PHYSICAL_DIGEST_INVALID",
            ),
            (
                turn_root / "attempt-00" / "raw-output.bin",
                turn.get("raw_output_digest"),
                "RAW_OUTPUT_PHYSICAL_DIGEST_INVALID",
            ),
            (
                wrapper_path,
                turn.get("deterministic_wrapper_digest"),
                "SEMANTIC_WRAPPER_PHYSICAL_DIGEST_INVALID",
            ),
        )
        for path, expected_digest, code in physical_paths:
            if (
                not isinstance(expected_digest, str)
                or len(expected_digest) != 64
                or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != expected_digest
            ):
                raise FormalE0BatchError(code)
        wrapper = load_json_strict(wrapper_path)
        verify_self_digest(wrapper, "record_digest")
        if wrapper.get("source_input_digest") != turn.get(
            "provider_input_digest"
        ):
            raise FormalE0BatchError("SEMANTIC_WRAPPER_BINDING_INVALID")
        semantic = wrapper.get("semantic_payload")
        if not isinstance(semantic, Mapping):
            raise FormalE0BatchError("SEMANTIC_PAYLOAD_MISSING")
        outputs.append(semantic)
    return tuple(outputs)


def _calculate_arm_score_once(
    *,
    topology_id: str,
    semantic_outputs: tuple[Mapping[str, Any], ...],
    package: DecisionInputPackage,
    account: FrozenAccountPolicy,
    sample_cohort: str,
) -> dict[str, Any]:
    candidates = {
        "PRIMARY": any(item.get("primary_path") for item in semantic_outputs),
        "ALTERNATIVE": any(
            isinstance(item.get("alternative_paths"), list)
            and bool(item["alternative_paths"])
            for item in semantic_outputs
        ),
        "NULL": any(item.get("null_path") for item in semantic_outputs),
        "OTHER_OR_UNKNOWN": any(
            item.get("other_or_unknown_path") for item in semantic_outputs
        ),
    }
    discovered = sorted(
        {
            str(claim["category"])
            for item in semantic_outputs
            for claim in item.get("challenge_claims", [])
            if isinstance(claim, Mapping)
            and claim.get("category") in CHALLENGE_CATEGORIES
        }
    )
    selected_action = semantic_outputs[-1].get("selected_action")
    if selected_action is not None and not isinstance(selected_action, str):
        selected_action = None
    preview = preview_action(
        package.state,
        selected_action_id=selected_action,
        current_mark=Decimal(str(package.current_bar["close"])),
        account=account,
    )
    non_selector_actions = sum(
        item.get("selected_action") is not None
        for item in semantic_outputs[:-1]
    )
    state_document = package.context_document["strategic_episode_state"]
    try:
        _validate_continuity_evidence(
            package.context_document["prior_accepted_analysis"],
            state=package.state,
            sample_index=package.sample_index,
        )
        continuity_valid = True
    except (KeyError, ValueError, TypeError):
        continuity_valid = False
    state_continuity = (
        isinstance(state_document, Mapping)
        and state_document.get("state_digest")
        == package.state.document()["state_digest"]
        and package.context_document.get("prior_accepted_head")
        == package.state.prior_accepted_head
        and continuity_valid
    )
    pit_valid = (
        package.context_document["pit_authority"][
            "future_visibility_count"
        ]
        == 0
        and package.context_document["pit_authority"][
            "future_outcome_values_in_role_input"
        ]
        is False
    )
    schema_valid = len(semantic_outputs) == 3
    coverage_count = sum(candidates.values())
    components = {
        "SCHEMA_VALIDITY": schema_valid,
        "PIT_VALIDITY": pit_valid,
        "STATE_CONTINUITY": state_continuity,
        "ACTION_FEASIBILITY": preview.action_exactly_feasible,
        "RISK_BUDGET_VALIDITY": preview.risk_budget_valid,
        "REENTRY_SYMMETRY": preview.reentry_symmetry_valid,
        "OPPORTUNITY_COST_CONSIDERATION": coverage_count >= 3,
    }
    hard_errors = (
        int(not preview.action_exactly_feasible)
        + int(not preview.risk_budget_valid)
        + int(not preview.reentry_symmetry_valid)
    )
    safety_failures = int(not pit_valid)
    state_errors = int(not state_continuity)
    role_overreach = non_selector_actions
    quality_count = sum(components.values())
    qualification = (
        "PASS"
        if (
            sample_cohort == "POLICY_QUALIFICATION"
            and quality_count >= 6
            and hard_errors == 0
            and safety_failures == 0
            and state_errors == 0
            and role_overreach == 0
        )
        else (
            "FAIL"
            if sample_cohort == "POLICY_QUALIFICATION"
            else "NOT_APPLICABLE"
        )
    )
    return {
        "topology_id": topology_id,
        "selected_action_id": selected_action,
        "candidate_components": candidates,
        "challenge_categories": discovered,
        "action_quality_components": components,
        "dynamic_candidate_coverage": Decimal(coverage_count) / Decimal(4),
        "material_challenge_coverage": Decimal(len(discovered))
        / Decimal(len(CHALLENGE_CATEGORIES)),
        "action_quality_score": Decimal(quality_count) / Decimal(7),
        "safety_state_pit_authority_failures": safety_failures,
        "role_overreach_failures": role_overreach,
        "hard_constraint_error_count": hard_errors,
        "state_continuity_error_count": state_errors,
        "qualification_verdict": qualification,
        "governance_preview": preview.payload(),
    }


def score_generation_arm(
    *,
    session_root: Path,
    generation_receipt: Mapping[str, Any],
    topology_id: str,
    package: DecisionInputPackage,
    account: FrozenAccountPolicy,
) -> DeterministicArmScore:
    """Score exact wrappers twice; caller-supplied scores are not accepted."""

    verify_self_digest(generation_receipt, "receipt_digest")
    common_digest = generation_receipt.get("common_context_digest")
    common_path = (
        Path(session_root)
        / "shared"
        / "byte-identical-common-context.json"
    )
    if (
        not isinstance(common_digest, str)
        or len(common_digest) != 64
        or not common_path.is_file()
        or hashlib.sha256(common_path.read_bytes()).hexdigest()
        != common_digest
    ):
        raise FormalE0BatchError("COMMON_CONTEXT_PHYSICAL_DIGEST_INVALID")
    arms = {
        item["topology_id"]: item
        for item in generation_receipt.get("arm_receipts", [])
        if isinstance(item, Mapping)
    }
    arm = arms.get(topology_id)
    if arm is None or arm.get("status") != "COMPLETE":
        raise FormalE0BatchError("GENERATION_ARM_INCOMPLETE")
    if (
        arm.get("common_context_digest") != common_digest
        or not isinstance(arm.get("raw_input_ref"), str)
        or common_digest not in str(arm["raw_input_ref"])
    ):
        raise FormalE0BatchError("GENERATION_COMMON_INPUT_REF_INVALID")
    outputs = _load_semantic_outputs(
        session_root=session_root, arm_receipt=arm
    )
    first = _calculate_arm_score_once(
        topology_id=topology_id,
        semantic_outputs=outputs,
        package=package,
        account=account,
        sample_cohort=package.cohort,
    )
    second = _calculate_arm_score_once(
        topology_id=topology_id,
        semantic_outputs=outputs,
        package=package,
        account=account,
        sample_cohort=package.cohort,
    )
    first_digest = canonical_digest(first)
    difference = int(first_digest != canonical_digest(second))
    calculation = self_digest(
        {
            "schema_id": "formal_e0_deterministic_arm_calculation",
            "schema_version": "1.0.0",
            "sample_index": package.sample_index,
            "sample_cohort": package.cohort,
            **first,
            "first_calculation_digest": first_digest,
            "second_calculation_digest": canonical_digest(second),
            "reproducibility_difference_count": difference,
        },
        "calculation_digest",
    )
    return DeterministicArmScore(
        topology_id=topology_id,
        semantic_outputs=outputs,
        selected_action_id=first["selected_action_id"],
        dynamic_candidate_coverage=first[
            "dynamic_candidate_coverage"
        ],
        material_challenge_coverage=first[
            "material_challenge_coverage"
        ],
        action_quality_score=first["action_quality_score"],
        action_quality_components=first["action_quality_components"],
        candidate_components=first["candidate_components"],
        discovered_challenge_categories=tuple(
            first["challenge_categories"]
        ),
        safety_state_pit_authority_failures=first[
            "safety_state_pit_authority_failures"
        ],
        role_overreach_failures=first["role_overreach_failures"],
        hard_constraint_error_count=first[
            "hard_constraint_error_count"
        ],
        state_continuity_error_count=first[
            "state_continuity_error_count"
        ],
        reproducibility_difference_count=difference,
        qualification_verdict=first["qualification_verdict"],
        calculation_digest=str(calculation["calculation_digest"]),
    )


def _arm_from_generation(
    receipt: Mapping[str, Any], topology_id: str
) -> Mapping[str, Any]:
    matches = [
        item
        for item in receipt.get("arm_receipts", [])
        if isinstance(item, Mapping) and item.get("topology_id") == topology_id
    ]
    if len(matches) != 1 or matches[0].get("status") != "COMPLETE":
        raise FormalE0BatchError("FORMAL_GENERATIVE_ARM_INCOMPLETE")
    return matches[0]


def _transport_attestation(
    generation_receipt: Mapping[str, Any],
) -> tuple[str, str]:
    value = generation_receipt.get("served_model_attestation")
    status = generation_receipt.get("served_model_attestation_status")
    if (
        not isinstance(value, str)
        or not value
        or status != "ATTESTED"
    ):
        raise FormalE0BatchError(
            "SERVED_MODEL_ATTESTATION_REQUIRED_FOR_FORMAL_OBSERVATION"
        )
    return value, str(status)


def _make_observation(
    *,
    prepared: PreparedFormalE0Run,
    generation_receipt: Mapping[str, Any],
    topology_id: str,
    score: DeterministicArmScore,
    transition: ReplayTransition,
    baseline: ReplayTransition | None,
) -> PairedObservationReceipt:
    arm = _arm_from_generation(generation_receipt, topology_id)
    served_model, served_status = _transport_attestation(
        generation_receipt
    )
    formal = score.qualification_verdict == "NOT_APPLICABLE" and (
        generation_receipt["sample_cohort"] == "FORMAL_EXPERIMENT"
    )
    return build_paired_observation_receipt(
        session_id=str(generation_receipt["paired_session_id"]),
        topology_id=topology_id,
        input_digest=str(generation_receipt["common_context_digest"]),
        model_class=str(generation_receipt["requested_model"]),
        total_budget_digest=str(generation_receipt["budget_limit_digest"]),
        dynamic_candidate_coverage=score.dynamic_candidate_coverage,
        material_challenge_coverage=(
            score.material_challenge_coverage
        ),
        action_quality_score=score.action_quality_score,
        safety_state_pit_authority_failures=(
            score.safety_state_pit_authority_failures
        ),
        role_overreach_failures=score.role_overreach_failures,
        model_calls=int(arm["calls_attempted"]),
        tokens=int(arm["usage"]["total_tokens"]),
        latency_ms=int(arm["latency_ms"]),
        cost_microunits=arm["cost_microunits"],
        timeout_count=int(arm["timeout_count"]),
        missing_role_count=int(arm["missing_role_count"]),
        sample_index=int(generation_receipt["sample_index"]),
        sample_cohort=str(generation_receipt["sample_cohort"]),
        qualification_verdict=score.qualification_verdict,
        formal_evidence=True,
        requested_model=str(generation_receipt["requested_model"]),
        served_model_attestation=served_model,
        served_model_attestation_status=served_status,
        parameter_digest=str(
            generation_receipt["model_configuration_digest"]
        ),
        budget_limit_digest=str(
            generation_receipt["budget_limit_digest"]
        ),
        transport_contract_verdict="PASS",
        transport_schema_digest=canonical_digest(
            ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
        ),
        dataset_digest=prepared.dataset_manifest_digest,
        formal_contract_digest=str(
            generation_receipt["formal_contract_digest"]
        ),
        scoring_policy_digest=prepared.scoring_policy_digest,
        cost_policy_digest=prepared.cost_policy_digest,
        initial_account_digest=prepared.initial_account_digest,
        termination_policy_digest=(
            prepared.termination_policy_digest
        ),
        raw_input_ref=str(arm["raw_input_ref"]),
        raw_output_refs=tuple(arm["raw_output_refs"]),
        usage_receipt_digest=str(arm["usage_receipt_digest"]),
        hard_constraint_error_count=(
            score.hard_constraint_error_count
        ),
        state_continuity_error_count=(
            score.state_continuity_error_count
        ),
        reproducibility_difference_count=(
            score.reproducibility_difference_count
        ),
        net_pnl_after_cost=(
            transition.net_pnl_after_cost_fraction if formal else None
        ),
        transaction_cost=(
            transition.transaction_cost_fraction if formal else None
        ),
        max_drawdown_fraction=(
            transition.max_drawdown_fraction if formal else None
        ),
        primary_path_capture=(
            transition.primary_path_capture if formal else None
        ),
        frozen_baseline_net_pnl_after_cost=(
            baseline.net_pnl_after_cost_fraction
            if formal and baseline is not None
            else None
        ),
        frozen_baseline_max_drawdown_fraction=(
            baseline.max_drawdown_fraction
            if formal and baseline is not None
            else None
        ),
        frozen_baseline_primary_path_capture=(
            baseline.primary_path_capture
            if formal and baseline is not None
            else None
        ),
    )


def _decision_receipt(
    *,
    prepared: PreparedFormalE0Run,
    package: DecisionInputPackage,
    generation_receipt: Mapping[str, Any],
    score: DeterministicArmScore,
    transition: ReplayTransition,
    baseline: ReplayTransition | None,
    observation: PairedObservationReceipt,
    state_application_mode: str,
) -> dict[str, Any]:
    outputs = list(score.semantic_outputs)
    value = {
        "schema_id": "formal_e0_complete_decision_receipt",
        "schema_version": "1.0.0",
        "run_bindings_digest": prepared.run_bindings_digest,
        "sample_index": package.sample_index,
        "sample_cohort": package.cohort,
        "topology_id": score.topology_id,
        "decision_context_digest": package.context_document[
            "context_digest"
        ],
        "prior_accepted_analysis_digest": package.context_document[
            "prior_accepted_analysis"
        ]["continuity_digest"],
        "proposal": outputs[0],
        "challenge": outputs[1],
        "selection": outputs[2],
        "calculation": {
            "calculation_digest": score.calculation_digest,
            "candidate_components": dict(score.candidate_components),
            "challenge_categories": (
                score.discovered_challenge_categories
            ),
            "action_quality_components": dict(
                score.action_quality_components
            ),
            "dynamic_candidate_coverage": (
                score.dynamic_candidate_coverage
            ),
            "material_challenge_coverage": (
                score.material_challenge_coverage
            ),
            "action_quality_score": score.action_quality_score,
        },
        "feasible_actions": package.context_document["feasible_actions"],
        "selected_action_id": score.selected_action_id,
        "governance": {
            "state_application_mode": state_application_mode,
            "natural_language_state_authority": "NONE",
            "model_selection_admitted": transition.preview.admitted,
            "preview": transition.preview.payload(),
            "qualification_verdict": score.qualification_verdict,
            "hard_constraint_error_count": (
                score.hard_constraint_error_count
            ),
            "state_continuity_error_count": (
                score.state_continuity_error_count
            ),
            "role_overreach_failures": score.role_overreach_failures,
            "safety_state_pit_authority_failures": (
                score.safety_state_pit_authority_failures
            ),
        },
        "state_transition": transition.receipt(),
        "portfolio": transition.receipt()["portfolio"],
        "frozen_baseline_transition": (
            baseline.receipt() if baseline is not None else None
        ),
        "generation_receipt_digest": generation_receipt["receipt_digest"],
        "paired_observation_receipt_digest": (
            observation.receipt_digest
        ),
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return self_digest(value, "receipt_digest")


def _load_generation_receipt(session_root: Path) -> Mapping[str, Any]:
    path = session_root / "paired-run-receipt.json"
    try:
        value = load_json_strict(path)
    except Exception as exc:
        raise FormalE0BatchError(
            "EXISTING_GENERATIVE_SESSION_INCOMPLETE_READ_ONLY"
        ) from exc
    verify_self_digest(value, "receipt_digest")
    return value


def _observation_path(
    prepared: PreparedFormalE0Run,
    cohort: str,
    sample_index: int,
    topology_id: str,
) -> Path:
    return (
        prepared.run_root
        / "observations"
        / COHORT_CODES[cohort]
        / f"{sample_index:03d}-{topology_id.casefold()}.json"
    )


def _decision_receipt_path(
    prepared: PreparedFormalE0Run,
    cohort: str,
    sample_index: int,
    topology_id: str,
) -> Path:
    return (
        prepared.run_root
        / "decisions"
        / COHORT_CODES[cohort]
        / f"{sample_index:03d}-{topology_id.casefold()}.json"
    )


def _context_path(
    prepared: PreparedFormalE0Run,
    cohort: str,
    sample_index: int,
) -> Path:
    return (
        prepared.run_root
        / "decision-inputs"
        / COHORT_CODES[cohort]
        / f"{sample_index:03d}.json"
    )


def _accepted_continuity_evidence(
    *,
    prepared: PreparedFormalE0Run,
    cohort: str,
    sample_index: int,
    selected_topology: str,
    state: StrategicEpisodeState,
    prior_receipt_path: Path,
    prior_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile and verify the previous accepted analysis handoff."""

    previous_index = sample_index - 1
    verify_self_digest(prior_receipt, "receipt_digest")
    if (
        prior_receipt.get("schema_id")
        != "formal_e0_complete_decision_receipt"
        or prior_receipt.get("sample_cohort") != cohort
        or prior_receipt.get("sample_index") != previous_index
        or prior_receipt.get("topology_id") != selected_topology
        or prior_receipt.get("run_bindings_digest")
        != prepared.run_bindings_digest
    ):
        raise FormalE0BatchError("PRIOR_DECISION_RECEIPT_BINDING_INVALID")
    transition = prior_receipt.get("state_transition")
    if not isinstance(transition, Mapping):
        raise FormalE0BatchError("PRIOR_STATE_TRANSITION_INVALID")
    verify_self_digest(transition, "receipt_digest")
    state_after = transition.get("state_after")
    if not isinstance(state_after, Mapping):
        raise FormalE0BatchError("PRIOR_STATE_AFTER_MISSING")
    verified_state = StrategicEpisodeState.from_document(state_after)
    if (
        verified_state.document() != state.document()
        or state.last_sample_index != previous_index
        or transition.get("transition_head_digest")
        != state.prior_accepted_head
    ):
        raise FormalE0BatchError("PRIOR_STATE_TRANSITION_CHAIN_BROKEN")
    prior_context_path = _context_path(prepared, cohort, previous_index)
    prior_context = load_json_strict(prior_context_path)
    verify_self_digest(prior_context, "context_digest")
    pit = prior_context.get("pit_authority")
    if (
        prior_context.get("sample_cohort") != cohort
        or prior_context.get("sample_index") != previous_index
        or prior_receipt.get("decision_context_digest")
        != prior_context.get("context_digest")
        or not isinstance(pit, Mapping)
        or pit.get("future_visibility_count") != 0
        or pit.get("future_outcome_values_in_role_input") is not False
        or pit.get("next_outcome_bar_id") is not None
    ):
        raise FormalE0BatchError("PRIOR_DECISION_CONTEXT_PIT_INVALID")
    selection = prior_receipt.get("selection")
    calculation = prior_receipt.get("calculation")
    governance = prior_receipt.get("governance")
    if (
        not isinstance(selection, Mapping)
        or selection.get("output_kind") != "SELECTION"
        or not isinstance(calculation, Mapping)
        or not isinstance(governance, Mapping)
    ):
        raise FormalE0BatchError("PRIOR_ACCEPTED_ANALYSIS_MISSING")
    selected_action = prior_receipt.get("selected_action_id")
    if selection.get("selected_action") != selected_action:
        raise FormalE0BatchError("PRIOR_ACCEPTED_ACTION_BINDING_INVALID")
    return _continuity_document(
        kind="ACCEPTED_SELECTOR_DECISION",
        state=state,
        expected_sample_index=sample_index,
        previous_sample_index=previous_index,
        previous_decision_receipt_ref={
            "artifact_kind": "WRITE_ONCE_COMPLETE_DECISION_RECEIPT",
            "relative_path": str(
                prior_receipt_path.relative_to(prepared.run_root)
            ),
            "receipt_digest": prior_receipt["receipt_digest"],
            "physical_sha256": hashlib.sha256(
                prior_receipt_path.read_bytes()
            ).hexdigest(),
        },
        previous_decision_context_ref={
            "artifact_kind": "WRITE_ONCE_DECISION_CONTEXT",
            "relative_path": str(
                prior_context_path.relative_to(prepared.run_root)
            ),
            "context_digest": prior_context["context_digest"],
            "physical_sha256": hashlib.sha256(
                prior_context_path.read_bytes()
            ).hexdigest(),
        },
        accepted_selector_semantic_payload=selection,
        calculation_summary={
            "calculation_digest": calculation.get("calculation_digest"),
            "candidate_components": calculation.get(
                "candidate_components"
            ),
            "challenge_categories": calculation.get(
                "challenge_categories"
            ),
            "action_quality_components": calculation.get(
                "action_quality_components"
            ),
            "dynamic_candidate_coverage": calculation.get(
                "dynamic_candidate_coverage"
            ),
            "material_challenge_coverage": calculation.get(
                "material_challenge_coverage"
            ),
            "action_quality_score": calculation.get(
                "action_quality_score"
            ),
        },
        governance_summary={
            "state_application_mode": governance.get(
                "state_application_mode"
            ),
            "natural_language_state_authority": governance.get(
                "natural_language_state_authority"
            ),
            "model_selection_admitted": governance.get(
                "model_selection_admitted"
            ),
            "qualification_verdict": governance.get(
                "qualification_verdict"
            ),
            "hard_constraint_error_count": governance.get(
                "hard_constraint_error_count"
            ),
            "state_continuity_error_count": governance.get(
                "state_continuity_error_count"
            ),
        },
        previous_selected_action_id=selected_action,
        previous_transition_head=str(transition["transition_head_digest"]),
    )


class FormalE0BatchRunner:
    """Resume-safe orchestrator for the three frozen cohorts."""

    def __init__(
        self,
        *,
        prepared_run_root: Path,
        model_port: GenerativeModelPort,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.prepared = load_prepared_formal_e0_run(prepared_run_root)
        self.model_port = model_port
        self.clock = clock
        self.dataset = _load_dataset(self.prepared)
        self.account = account_policy_from_documents(
            load_json_strict(self.prepared.initial_account_path),
            load_json_strict(self.prepared.cost_policy_path),
        )

    def preflight(self) -> Mapping[str, Any]:
        receipt = assess_formal_transport(
            prepared=self.prepared,
            model_port=self.model_port,
        )
        write_resume_json(
            self.prepared.run_root
            / "preflight"
            / "transport-admission.json",
            receipt,
        )
        return receipt

    def _require_preflight(self) -> None:
        receipt = self.preflight()
        if receipt["status"] != "PASS":
            raise FormalE0BatchError(
                "FORMAL_GENERATIVE_CALL_NO_GO:"
                + ",".join(receipt["reason_codes"])
            )

    def _generate(
        self,
        *,
        package: DecisionInputPackage,
        topology_ids: tuple[str, ...],
        selected_topology_id: str | None,
        selection_digest: str | None,
    ) -> tuple[Mapping[str, Any], Path]:
        request = build_generation_request(
            prepared=self.prepared,
            package=package,
            topology_ids=topology_ids,
            selected_topology_id=selected_topology_id,
            topology_selection_result_digest=selection_digest,
        )
        session_root = (
            self.prepared.run_root
            / "sessions"
            / request.paired_session_id
        )
        if session_root.exists():
            return _load_generation_receipt(session_root), session_root
        try:
            archive = WriteOncePairedRunArchive(
                self.prepared.run_root / "sessions",
                request.paired_session_id,
            )
        except PairedRunArchiveError as exc:
            raise FormalE0BatchError(str(exc)) from exc
        receipt = run_paired_generative_topologies(
            request,
            model_port=self.model_port,
            archive=archive,
            clock=self.clock,
        )
        if receipt.get("formal_evidence") is not True:
            raise FormalE0BatchError(
                "GENERATIVE_RUN_NOT_FORMAL_EVIDENCE:"
                + ",".join(receipt.get("reason_codes", []))
            )
        return receipt, archive.root_path

    def _persist_context(self, package: DecisionInputPackage) -> None:
        write_resume_json(
            _context_path(
                self.prepared, package.cohort, package.sample_index
            ),
            package.context_document,
        )

    def _selection_reference_packages(
        self,
    ) -> dict[int, tuple[DecisionInputPackage, ReplayTransition]]:
        """Precompute a model-independent state chain for all paired arms."""

        cohort = "TOPOLOGY_SELECTION"
        first = self.dataset.current_bar(96)
        state = initial_episode_state(
            cohort=cohort,
            first_mark=Decimal(str(first["close"])),
            account=self.account,
            episode_id=f"{self.prepared.run_id}:selection-reference",
        )
        continuity = _genesis_continuity_evidence(state, 96)
        packages: dict[int, tuple[DecisionInputPackage, ReplayTransition]] = {}
        for index in COHORT_RANGES[cohort]:
            package = build_decision_input_package(
                prepared=self.prepared,
                dataset=self.dataset,
                state=state,
                sample_index=index,
                account=self.account,
                continuity_evidence=continuity,
            )
            control = replay_action_one_hour(
                state,
                selected_action_id=frozen_reference_action(state),
                sample_index=index,
                current_bar=package.current_bar,
                next_bar=package.next_bar,
                account=self.account,
                control_mode="PAIRED_REFERENCE_CONTROL",
            )
            packages[index] = (package, control)
            state = control.state_after
            continuity = _selection_reference_continuity_evidence(
                prepared=self.prepared,
                transition=control,
                expected_sample_index=index + 1,
            )
        return packages

    def _complete_selection_index(
        self,
        *,
        package: DecisionInputPackage,
        control: ReplayTransition,
    ) -> tuple[PairedObservationReceipt, ...]:
        self._persist_context(package)
        generation, session_root = self._generate(
            package=package,
            topology_ids=FORMAL_TOPOLOGY_IDS,
            selected_topology_id=None,
            selection_digest=None,
        )
        observations = []
        for topology_id in FORMAL_TOPOLOGY_IDS:
            observation_path = _observation_path(
                self.prepared,
                package.cohort,
                package.sample_index,
                topology_id,
            )
            if observation_path.exists():
                observations.append(
                    load_paired_observation_receipt(observation_path)
                )
                continue
            score = score_generation_arm(
                session_root=session_root,
                generation_receipt=generation,
                topology_id=topology_id,
                package=package,
                account=self.account,
            )
            observation = _make_observation(
                prepared=self.prepared,
                generation_receipt=generation,
                topology_id=topology_id,
                score=score,
                transition=control,
                baseline=None,
            )
            receipt = _decision_receipt(
                prepared=self.prepared,
                package=package,
                generation_receipt=generation,
                score=score,
                transition=control,
                baseline=None,
                observation=observation,
                state_application_mode="PAIRED_REFERENCE_CONTROL",
            )
            write_resume_json(
                _decision_receipt_path(
                    self.prepared,
                    package.cohort,
                    package.sample_index,
                    topology_id,
                ),
                receipt,
            )
            write_resume_json(observation_path, asdict(observation))
            observations.append(observation)
        return tuple(observations)

    def run_selection(
        self,
        *,
        indices: Sequence[int] | None = None,
        concurrency: int = 1,
    ) -> tuple[PairedObservationReceipt, ...]:
        self._require_preflight()
        if type(concurrency) is not int or not (1 <= concurrency <= 16):
            raise FormalE0BatchError("CONCURRENCY_INVALID")
        selected_indices = tuple(
            COHORT_RANGES["TOPOLOGY_SELECTION"]
            if indices is None
            else indices
        )
        if (
            len(set(selected_indices)) != len(selected_indices)
            or any(
                index not in COHORT_RANGES["TOPOLOGY_SELECTION"]
                for index in selected_indices
            )
        ):
            raise FormalE0BatchError("SELECTION_INDICES_INVALID")
        packages = self._selection_reference_packages()
        rows: list[PairedObservationReceipt] = []
        if concurrency == 1:
            for index in selected_indices:
                rows.extend(
                    self._complete_selection_index(
                        package=packages[index][0],
                        control=packages[index][1],
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(
                        self._complete_selection_index,
                        package=packages[index][0],
                        control=packages[index][1],
                    ): index
                    for index in selected_indices
                }
                for future in as_completed(futures):
                    rows.extend(future.result())
        rows.sort(key=lambda item: (item.sample_index, item.topology_id))
        self.materialize_topology_selection_if_complete()
        return tuple(rows)

    def _all_observations(
        self, cohort: str
    ) -> tuple[PairedObservationReceipt, ...]:
        root = self.prepared.run_root / "observations" / COHORT_CODES[cohort]
        if not root.is_dir():
            return ()
        return tuple(
            load_paired_observation_receipt(path)
            for path in sorted(root.glob("*.json"))
        )

    def materialize_topology_selection_if_complete(
        self,
    ) -> Mapping[str, Any] | None:
        rows = self._all_observations("TOPOLOGY_SELECTION")
        if len(rows) != 96:
            return None
        result = evaluate_agent_topologies(
            tuple(item.to_topology_observation() for item in rows),
            minimum_paired_sessions=32,
            compared_topology_ids=FORMAL_TOPOLOGY_IDS,
        )
        value = self_digest(
            {
                "schema_id": "formal_e0_topology_selection_gate",
                "schema_version": "1.0.0",
                "evaluation": asdict(result),
                "selected_topology_id": result.selected_topology_id,
                "selection_result_digest": result.result_digest,
                "complete_paired_session_count": (
                    result.observed_complete_paired_sessions
                ),
                "state_source": (
                    "PRE_FROZEN_REFERENCE_STATE_SAME_FOR_ALL_ARMS"
                ),
                "status": (
                    "PASS"
                    if result.observed_complete_paired_sessions == 32
                    and result.equal_input_model_budget_verified
                    and result.selection_status
                    != "FAIL_INVALID_EXPERIMENT"
                    else "FAIL"
                ),
                "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
                "external_execution_authority": "NONE_E0",
                "executable": False,
            },
            "receipt_digest",
        )
        write_resume_json(
            self.prepared.run_root
            / "gates"
            / "topology-selection.json",
            value,
        )
        return value

    def _load_selection_gate(self) -> Mapping[str, Any]:
        path = (
            self.prepared.run_root
            / "gates"
            / "topology-selection.json"
        )
        if not path.exists():
            self.materialize_topology_selection_if_complete()
        value = load_json_strict(path)
        verify_self_digest(value, "receipt_digest")
        if value.get("status") != "PASS":
            raise FormalE0BatchError("TOPOLOGY_SELECTION_GATE_NOT_PASS")
        return value

    def _load_prior_states(
        self,
        *,
        cohort: str,
        sample_index: int,
    ) -> tuple[
        StrategicEpisodeState,
        StrategicEpisodeState | None,
        Mapping[str, Any],
    ]:
        start = COHORT_RANGES[cohort].start
        if sample_index == start:
            current = self.dataset.current_bar(sample_index)
            state = initial_episode_state(
                cohort=cohort,
                first_mark=Decimal(str(current["close"])),
                account=self.account,
                episode_id=(
                    f"{self.prepared.run_id}:{COHORT_CODES[cohort]}"
                ),
            )
            baseline = (
                initial_episode_state(
                    cohort=cohort,
                    first_mark=Decimal(str(current["close"])),
                    account=self.account,
                    episode_id=f"{self.prepared.run_id}:formal-baseline",
                )
                if cohort == "FORMAL_EXPERIMENT"
                else None
            )
            return (
                state,
                baseline,
                _genesis_continuity_evidence(state, sample_index),
            )
        topology = str(self._load_selection_gate()["selected_topology_id"])
        prior_path = _decision_receipt_path(
            self.prepared, cohort, sample_index - 1, topology
        )
        if not prior_path.exists():
            raise FormalE0BatchError(
                "SEQUENTIAL_PRIOR_STATE_MISSING_RUN_CONTIGUOUSLY"
            )
        receipt = load_json_strict(prior_path)
        verify_self_digest(receipt, "receipt_digest")
        transition = receipt.get("state_transition")
        if not isinstance(transition, Mapping):
            raise FormalE0BatchError("PRIOR_STATE_TRANSITION_INVALID")
        state_after = transition.get("state_after")
        if not isinstance(state_after, Mapping):
            raise FormalE0BatchError("PRIOR_STATE_AFTER_MISSING")
        state = StrategicEpisodeState.from_document(state_after)
        baseline_state = None
        if cohort == "FORMAL_EXPERIMENT":
            baseline_transition = receipt.get(
                "frozen_baseline_transition"
            )
            if not isinstance(baseline_transition, Mapping):
                raise FormalE0BatchError("PRIOR_BASELINE_STATE_MISSING")
            baseline_after = baseline_transition.get("state_after")
            if not isinstance(baseline_after, Mapping):
                raise FormalE0BatchError("PRIOR_BASELINE_STATE_INVALID")
            baseline_state = StrategicEpisodeState.from_document(
                baseline_after
            )
        continuity = _accepted_continuity_evidence(
            prepared=self.prepared,
            cohort=cohort,
            sample_index=sample_index,
            selected_topology=topology,
            state=state,
            prior_receipt_path=prior_path,
            prior_receipt=receipt,
        )
        return state, baseline_state, continuity

    def _complete_sequential_index(
        self,
        *,
        cohort: str,
        sample_index: int,
        selected_topology: str,
        selection_digest: str,
    ) -> SampleCompletion:
        observation_path = _observation_path(
            self.prepared, cohort, sample_index, selected_topology
        )
        decision_path = _decision_receipt_path(
            self.prepared, cohort, sample_index, selected_topology
        )
        if observation_path.exists() and decision_path.exists():
            observation = load_paired_observation_receipt(observation_path)
            receipt = load_json_strict(decision_path)
            verify_self_digest(receipt, "receipt_digest")
            state = StrategicEpisodeState.from_document(
                receipt["state_transition"]["state_after"]
            )
            baseline = (
                StrategicEpisodeState.from_document(
                    receipt["frozen_baseline_transition"]["state_after"]
                )
                if cohort == "FORMAL_EXPERIMENT"
                else None
            )
            return SampleCompletion(
                observation=observation,
                decision_receipt=receipt,
                state_after=state,
                baseline_state_after=baseline,
            )
        if observation_path.exists() != decision_path.exists():
            raise FormalE0BatchError(
                "RESUME_ARTIFACT_SET_PARTIAL_NEVER_OVERWRITE"
            )
        state, baseline_state, continuity = self._load_prior_states(
            cohort=cohort, sample_index=sample_index
        )
        package = build_decision_input_package(
            prepared=self.prepared,
            dataset=self.dataset,
            state=state,
            sample_index=sample_index,
            account=self.account,
            continuity_evidence=continuity,
        )
        self._persist_context(package)
        generation, session_root = self._generate(
            package=package,
            topology_ids=(selected_topology,),
            selected_topology_id=selected_topology,
            selection_digest=selection_digest,
        )
        score = score_generation_arm(
            session_root=session_root,
            generation_receipt=generation,
            topology_id=selected_topology,
            package=package,
            account=self.account,
        )
        transition = replay_action_one_hour(
            state,
            selected_action_id=score.selected_action_id,
            sample_index=sample_index,
            current_bar=package.current_bar,
            next_bar=package.next_bar,
            account=self.account,
            control_mode="MODEL_SELECTED",
        )
        baseline_transition = None
        if cohort == "FORMAL_EXPERIMENT":
            if baseline_state is None:
                raise FormalE0BatchError("FORMAL_BASELINE_STATE_MISSING")
            baseline_transition = replay_action_one_hour(
                baseline_state,
                selected_action_id=frozen_reference_action(
                    baseline_state
                ),
                sample_index=sample_index,
                current_bar=package.current_bar,
                next_bar=package.next_bar,
                account=self.account,
                control_mode="FROZEN_BASELINE",
            )
        observation = _make_observation(
            prepared=self.prepared,
            generation_receipt=generation,
            topology_id=selected_topology,
            score=score,
            transition=transition,
            baseline=baseline_transition,
        )
        receipt = _decision_receipt(
            prepared=self.prepared,
            package=package,
            generation_receipt=generation,
            score=score,
            transition=transition,
            baseline=baseline_transition,
            observation=observation,
            state_application_mode="MODEL_EXACT_ACTION_ID",
        )
        write_resume_json(decision_path, receipt)
        write_resume_json(observation_path, asdict(observation))
        return SampleCompletion(
            observation=observation,
            decision_receipt=receipt,
            state_after=transition.state_after,
            baseline_state_after=(
                baseline_transition.state_after
                if baseline_transition is not None
                else None
            ),
        )

    def run_policy_qualification(
        self,
        *,
        indices: Sequence[int] | None = None,
        concurrency: int = 1,
    ) -> tuple[PairedObservationReceipt, ...]:
        self._require_preflight()
        if concurrency != 1:
            raise FormalE0BatchError(
                "SEQUENTIAL_STATE_COHORT_REQUIRES_CONCURRENCY_ONE"
            )
        gate = self._load_selection_gate()
        selected = str(gate["selected_topology_id"])
        digest = str(gate["selection_result_digest"])
        requested = tuple(
            COHORT_RANGES["POLICY_QUALIFICATION"]
            if indices is None
            else indices
        )
        if (
            not requested
            or tuple(sorted(requested)) != requested
            or any(
                item not in COHORT_RANGES["POLICY_QUALIFICATION"]
                for item in requested
            )
        ):
            raise FormalE0BatchError("QUALIFICATION_INDICES_INVALID")
        rows = []
        for index in requested:
            rows.append(
                self._complete_sequential_index(
                    cohort="POLICY_QUALIFICATION",
                    sample_index=index,
                    selected_topology=selected,
                    selection_digest=digest,
                ).observation
            )
        self.materialize_qualification_gate_if_complete()
        return tuple(rows)

    def materialize_qualification_gate_if_complete(
        self,
    ) -> Mapping[str, Any] | None:
        rows = self._all_observations("POLICY_QUALIFICATION")
        if len(rows) != 32:
            return None
        indices = {item.sample_index for item in rows}
        status = (
            "PASS"
            if indices == set(COHORT_RANGES["POLICY_QUALIFICATION"])
            and all(item.qualification_verdict == "PASS" for item in rows)
            and sum(item.hard_constraint_error_count for item in rows) == 0
            and sum(item.state_continuity_error_count for item in rows) == 0
            else "FAIL"
        )
        value = self_digest(
            {
                "schema_id": "formal_e0_policy_qualification_gate",
                "schema_version": "1.0.0",
                "selected_topology_id": rows[0].topology_id,
                "decision_count": len(rows),
                "pass_count": sum(
                    item.qualification_verdict == "PASS"
                    for item in rows
                ),
                "hard_constraint_error_count": sum(
                    item.hard_constraint_error_count for item in rows
                ),
                "state_continuity_error_count": sum(
                    item.state_continuity_error_count for item in rows
                ),
                "state_source": (
                    "INDEPENDENT_QUALIFICATION_GENESIS_NO_SELECTION_"
                    "POSITION_INHERITANCE"
                ),
                "status": status,
                "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
                "external_execution_authority": "NONE_E0",
                "executable": False,
            },
            "receipt_digest",
        )
        write_resume_json(
            self.prepared.run_root
            / "gates"
            / "policy-qualification.json",
            value,
        )
        return value

    def _require_qualification_gate(self) -> Mapping[str, Any]:
        path = (
            self.prepared.run_root
            / "gates"
            / "policy-qualification.json"
        )
        if not path.exists():
            self.materialize_qualification_gate_if_complete()
        value = load_json_strict(path)
        verify_self_digest(value, "receipt_digest")
        if value.get("status") != "PASS":
            raise FormalE0BatchError("POLICY_QUALIFICATION_GATE_NOT_PASS")
        return value

    def run_formal(
        self,
        *,
        indices: Sequence[int] | None = None,
        concurrency: int = 1,
    ) -> tuple[PairedObservationReceipt, ...]:
        self._require_preflight()
        if concurrency != 1:
            raise FormalE0BatchError(
                "SEQUENTIAL_STATE_COHORT_REQUIRES_CONCURRENCY_ONE"
            )
        self._require_qualification_gate()
        selection = self._load_selection_gate()
        selected = str(selection["selected_topology_id"])
        digest = str(selection["selection_result_digest"])
        requested = tuple(
            COHORT_RANGES["FORMAL_EXPERIMENT"]
            if indices is None
            else indices
        )
        if (
            not requested
            or tuple(sorted(requested)) != requested
            or any(
                item not in COHORT_RANGES["FORMAL_EXPERIMENT"]
                for item in requested
            )
        ):
            raise FormalE0BatchError("FORMAL_INDICES_INVALID")
        rows = []
        for index in requested:
            rows.append(
                self._complete_sequential_index(
                    cohort="FORMAL_EXPERIMENT",
                    sample_index=index,
                    selected_topology=selected,
                    selection_digest=digest,
                ).observation
            )
        return tuple(rows)


def parse_index_expression(
    value: str | None, *, cohort: str
) -> tuple[int, ...] | None:
    if value is None:
        return None
    expected = COHORT_RANGES.get(cohort)
    if expected is None:
        raise FormalE0BatchError("COHORT_INVALID")
    result: list[int] = []
    for part in value.split(","):
        token = part.strip()
        if not token:
            raise FormalE0BatchError("INDEX_EXPRESSION_INVALID")
        if "-" in token:
            pieces = token.split("-", 1)
            try:
                start, end = int(pieces[0]), int(pieces[1])
            except ValueError as exc:
                raise FormalE0BatchError(
                    "INDEX_EXPRESSION_INVALID"
                ) from exc
            if start > end:
                raise FormalE0BatchError("INDEX_EXPRESSION_INVALID")
            result.extend(range(start, end + 1))
        else:
            try:
                result.append(int(token))
            except ValueError as exc:
                raise FormalE0BatchError(
                    "INDEX_EXPRESSION_INVALID"
                ) from exc
    if (
        len(set(result)) != len(result)
        or any(index not in expected for index in result)
    ):
        raise FormalE0BatchError("INDEX_EXPRESSION_INVALID")
    return tuple(sorted(result))


__all__ = [
    "COHORT_RANGES",
    "DecisionInputPackage",
    "DeterministicArmScore",
    "FormalE0BatchError",
    "FormalE0BatchRunner",
    "FrozenDatasetView",
    "SampleCompletion",
    "assess_formal_transport",
    "build_decision_input_package",
    "build_generation_request",
    "parse_index_expression",
    "score_generation_arm",
]
