"""Formal E0 experiment contracts and deterministic orchestration.

This use case consumes already-frozen dataset and generative-run receipts.  It
does not collect market data, call a model, mutate V1, or instantiate the
second-round account.  The three frozen sample cohorts remain disjoint:

* topology selection: compare every registered topology;
* policy qualification: evaluate only the topology selected above;
* formal experiment: report behavior, risk, and economic outcomes without
  feeding them back into topology or policy selection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import re
from typing import Mapping

from ..domain.contracts.canonical import canonical_digest
from .generative_topology_run import ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
from .topology_evaluation import (
    TOPOLOGY_IDS,
    TopologyEvaluationResult,
    TopologyObservation,
    evaluate_agent_topologies,
)


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MUTABLE_ALIASES = {"current", "latest"}
FORMAL_E0_CONTRACT_DIGEST = (
    "92a3ef3cfb150e6f17bbc0ded71bdb5674531effab05990084e366397344ec3a"
)
FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST = canonical_digest(
    ROLE_INPUT_DOCUMENT_REPAIR_SCHEMA
)
_COHORTS = (
    "TOPOLOGY_SELECTION",
    "POLICY_QUALIFICATION",
    "FORMAL_EXPERIMENT",
)
_QUALIFICATION_VERDICTS = ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE")


class FormalExperimentError(ValueError):
    """A fail-closed formal-experiment contract violation."""


def _require_digest(value: str, code: str) -> None:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise FormalExperimentError(code)


def _require_immutable_ref(value: str, code: str) -> None:
    if not isinstance(value, str) or not value:
        raise FormalExperimentError(code)
    parts = {
        part.casefold()
        for part in re.split(r"[/\\:]", value)
        if part
    }
    if parts & _MUTABLE_ALIASES:
        raise FormalExperimentError(code)


def _require_run_id(value: str) -> None:
    if (
        not isinstance(value, str)
        or _RUN_ID.fullmatch(value) is None
        or value.casefold() in _MUTABLE_ALIASES
    ):
        raise FormalExperimentError(
            "EXPLICIT_IMMUTABLE_RUN_ID_REQUIRED"
        )


def _require_decimal(
    value: Decimal,
    code: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or (minimum is not None and value < minimum)
        or (maximum is not None and value > maximum)
    ):
        raise FormalExperimentError(code)


@dataclass(frozen=True, slots=True)
class FormalExperimentContract:
    contract_digest: str
    topology_ids: tuple[str, ...]
    requested_model: str
    topology_selection_indices: tuple[int, ...]
    policy_qualification_indices: tuple[int, ...]
    formal_experiment_indices: tuple[int, ...]
    minimum_complete_paired_sessions: int
    data_quality_required: str
    role_transport_contract_required: str
    hard_safety_failures_allowed: int
    second_round_requires_behavior_and_economic_gate: bool

    def __post_init__(self) -> None:
        _require_digest(
            self.contract_digest,
            "FORMAL_EXPERIMENT_CONTRACT_DIGEST_INVALID",
        )
        cohorts = (
            self.topology_selection_indices,
            self.policy_qualification_indices,
            self.formal_experiment_indices,
        )
        if (
            self.contract_digest != FORMAL_E0_CONTRACT_DIGEST
            or self.topology_ids != TOPOLOGY_IDS
            or not isinstance(self.requested_model, str)
            or not self.requested_model
            or self.minimum_complete_paired_sessions != 32
            or self.data_quality_required != "PASS"
            or self.role_transport_contract_required != "PASS"
            or self.hard_safety_failures_allowed != 0
            or not self.second_round_requires_behavior_and_economic_gate
            or cohorts
            != (
                tuple(range(96, 128)),
                tuple(range(128, 160)),
                tuple(range(160, 192)),
            )
        ):
            raise FormalExperimentError(
                "FORMAL_EXPERIMENT_CONTRACT_INVALID"
            )


@dataclass(frozen=True, slots=True)
class DatasetManifestRef:
    dataset_id: str
    dataset_digest: str
    quality_verdict: str
    decision_slot_count: int
    transport_contract_verdict: str
    transport_schema_digest: str

    def __post_init__(self) -> None:
        _require_immutable_ref(
            self.dataset_id,
            "DATASET_MANIFEST_ID_MUTABLE_OR_INVALID",
        )
        _require_digest(
            self.dataset_digest,
            "DATASET_MANIFEST_DIGEST_INVALID",
        )
        _require_digest(
            self.transport_schema_digest,
            "ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST_INVALID",
        )
        if (
            type(self.decision_slot_count) is not int
            or self.decision_slot_count < 0
        ):
            raise FormalExperimentError("DATASET_DECISION_SLOT_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class PairedObservationReceipt:
    # Exact TopologyObservation fields.
    session_id: str
    topology_id: str
    input_digest: str
    model_class: str
    total_budget_digest: str
    dynamic_candidate_coverage: Decimal
    material_challenge_coverage: Decimal
    action_quality_score: Decimal
    safety_state_pit_authority_failures: int
    role_overreach_failures: int
    model_calls: int
    tokens: int
    latency_ms: int
    cost_microunits: int | None
    timeout_count: int
    missing_role_count: int
    # Frozen formal-evidence bindings.
    sample_index: int
    sample_cohort: str
    qualification_verdict: str
    formal_evidence: bool
    requested_model: str
    served_model_attestation: str | None
    served_model_attestation_status: str
    parameter_digest: str
    budget_limit_digest: str
    transport_contract_verdict: str
    transport_schema_digest: str
    dataset_digest: str
    formal_contract_digest: str
    scoring_policy_digest: str
    cost_policy_digest: str
    initial_account_digest: str
    termination_policy_digest: str
    raw_input_ref: str
    raw_output_refs: tuple[str, ...]
    usage_receipt_digest: str
    # Deterministically scored behavior/risk/economic observations.
    hard_constraint_error_count: int
    state_continuity_error_count: int
    reproducibility_difference_count: int
    net_pnl_after_cost: Decimal | None
    transaction_cost: Decimal | None
    max_drawdown_fraction: Decimal | None
    primary_path_capture: Decimal | None
    frozen_baseline_net_pnl_after_cost: Decimal | None
    frozen_baseline_max_drawdown_fraction: Decimal | None
    frozen_baseline_primary_path_capture: Decimal | None
    receipt_digest: str

    def __post_init__(self) -> None:
        # Reuse the existing topology contract for its complete validation.
        self.to_topology_observation()
        for value, code in (
            (self.parameter_digest, "PARAMETER_DIGEST_INVALID"),
            (self.budget_limit_digest, "BUDGET_LIMIT_DIGEST_INVALID"),
            (
                self.transport_schema_digest,
                "ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST_INVALID",
            ),
            (self.dataset_digest, "RECEIPT_DATASET_DIGEST_INVALID"),
            (
                self.formal_contract_digest,
                "RECEIPT_FORMAL_CONTRACT_DIGEST_INVALID",
            ),
            (
                self.scoring_policy_digest,
                "RECEIPT_SCORING_POLICY_DIGEST_INVALID",
            ),
            (
                self.cost_policy_digest,
                "RECEIPT_COST_POLICY_DIGEST_INVALID",
            ),
            (
                self.initial_account_digest,
                "RECEIPT_INITIAL_ACCOUNT_DIGEST_INVALID",
            ),
            (
                self.termination_policy_digest,
                "RECEIPT_TERMINATION_POLICY_DIGEST_INVALID",
            ),
            (self.usage_receipt_digest, "USAGE_RECEIPT_DIGEST_INVALID"),
            (self.receipt_digest, "PAIRED_OBSERVATION_DIGEST_INVALID"),
        ):
            _require_digest(value, code)
        _require_immutable_ref(
            self.raw_input_ref,
            "RAW_INPUT_REF_MUTABLE_OR_INVALID",
        )
        if (
            not isinstance(self.raw_output_refs, tuple)
            or not self.raw_output_refs
            or len(set(self.raw_output_refs)) != len(self.raw_output_refs)
        ):
            raise FormalExperimentError("RAW_OUTPUT_REFS_INVALID")
        for value in self.raw_output_refs:
            _require_immutable_ref(value, "RAW_OUTPUT_REF_MUTABLE_OR_INVALID")
        if (
            type(self.sample_index) is not int
            or self.sample_index < 0
            or self.sample_cohort not in _COHORTS
            or self.qualification_verdict not in _QUALIFICATION_VERDICTS
            or self.formal_evidence is not True
            or not isinstance(self.requested_model, str)
            or not self.requested_model
            or (
                self.served_model_attestation is not None
                and not self.served_model_attestation
            )
            or self.served_model_attestation_status
            not in (
                "ATTESTED",
                "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT",
            )
            or (
                self.served_model_attestation is None
                and self.served_model_attestation_status
                != "UNKNOWN_NOT_EXPOSED_BY_PROVIDER_TRANSPORT"
            )
            or (
                self.served_model_attestation is not None
                and self.served_model_attestation_status != "ATTESTED"
            )
            or self.transport_contract_verdict != "PASS"
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.hard_constraint_error_count,
                    self.state_continuity_error_count,
                    self.reproducibility_difference_count,
                )
            )
            or (
                self.cost_microunits is not None
                and (
                    type(self.cost_microunits) is not int
                    or self.cost_microunits < 0
                )
            )
        ):
            raise FormalExperimentError(
                "PAIRED_OBSERVATION_FORMAL_EVIDENCE_INVALID"
            )
        economic_values = (
            (self.net_pnl_after_cost, "NET_PNL_AFTER_COST_INVALID", None, None),
            (
                self.frozen_baseline_net_pnl_after_cost,
                "BASELINE_PNL_INVALID",
                None,
                None,
            ),
            (
                self.transaction_cost,
                "TRANSACTION_COST_INVALID",
                Decimal(0),
                None,
            ),
            (
                self.max_drawdown_fraction,
                "MAX_DRAWDOWN_INVALID",
                Decimal(0),
                Decimal(1),
            ),
            (
                self.frozen_baseline_max_drawdown_fraction,
                "BASELINE_MAX_DRAWDOWN_INVALID",
                Decimal(0),
                Decimal(1),
            ),
            (
                self.primary_path_capture,
                "PRIMARY_PATH_CAPTURE_INVALID",
                Decimal(0),
                Decimal(1),
            ),
            (
                self.frozen_baseline_primary_path_capture,
                "BASELINE_PRIMARY_PATH_CAPTURE_INVALID",
                Decimal(0),
                Decimal(1),
            ),
        )
        if self.sample_cohort == "FORMAL_EXPERIMENT" and any(
            value is None for value, _, _, _ in economic_values
        ):
            raise FormalExperimentError(
                "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE"
            )
        for value, code, minimum, maximum in economic_values:
            if value is not None:
                _require_decimal(
                    value,
                    code,
                    minimum=minimum,
                    maximum=maximum,
                )
        if canonical_digest(self.digest_payload()) != self.receipt_digest:
            raise FormalExperimentError(
                "PAIRED_OBSERVATION_DIGEST_MISMATCH"
            )

    def to_topology_observation(self) -> TopologyObservation:
        return TopologyObservation(
            session_id=self.session_id,
            topology_id=self.topology_id,
            input_digest=self.input_digest,
            model_class=self.model_class,
            total_budget_digest=self.total_budget_digest,
            dynamic_candidate_coverage=self.dynamic_candidate_coverage,
            material_challenge_coverage=self.material_challenge_coverage,
            action_quality_score=self.action_quality_score,
            safety_state_pit_authority_failures=(
                self.safety_state_pit_authority_failures
            ),
            role_overreach_failures=self.role_overreach_failures,
            model_calls=self.model_calls,
            tokens=self.tokens,
            latency_ms=self.latency_ms,
            cost_microunits=self.cost_microunits,
            timeout_count=self.timeout_count,
            missing_role_count=self.missing_role_count,
        )

    def digest_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("receipt_digest")
        return payload


def build_paired_observation_receipt(
    **fields: object,
) -> PairedObservationReceipt:
    """Construct one receipt and compute its canonical self digest."""

    if "receipt_digest" in fields:
        raise FormalExperimentError(
            "PAIRED_OBSERVATION_DIGEST_CALLER_SUPPLIED"
        )
    return PairedObservationReceipt(
        **fields,
        receipt_digest=canonical_digest(fields),
    )


@dataclass(frozen=True, slots=True)
class FormalBehaviorMetrics:
    topology_id: str
    decision_count: int
    mean_dynamic_candidate_coverage: Decimal
    mean_independent_defect_discovery: Decimal
    mean_action_quality_score: Decimal
    hard_constraint_error_count: int
    state_continuity_error_count: int
    reproducibility_difference_count: int
    gate_status: str
    metrics_digest: str


@dataclass(frozen=True, slots=True)
class FormalRiskMetrics:
    topology_id: str
    safety_state_pit_authority_failures: int
    role_overreach_failures: int
    timeout_count: int
    missing_role_count: int
    max_drawdown_fraction: Decimal
    frozen_baseline_max_drawdown_fraction: Decimal
    drawdown_degradation_fraction: Decimal
    gate_status: str
    metrics_digest: str


@dataclass(frozen=True, slots=True)
class FormalProfitMetrics:
    topology_id: str
    net_pnl_after_cost: Decimal
    frozen_baseline_net_pnl_after_cost: Decimal
    relative_frozen_baseline_pnl: Decimal
    transaction_cost: Decimal
    mean_primary_path_capture: Decimal
    frozen_baseline_mean_primary_path_capture: Decimal
    gate_status: str
    metrics_digest: str


@dataclass(frozen=True, slots=True)
class FormalExperimentResult:
    offline_run_id: str
    dataset_manifest_ref: DatasetManifestRef
    experiment_contract_digest: str
    receipt_count: int
    topology_selection_session_count: int
    policy_qualification_session_count: int
    formal_experiment_session_count: int
    authority_snapshot: Mapping[str, object]
    experiment_manifest: Mapping[str, object]
    topology_evaluation: TopologyEvaluationResult
    behavior_metrics: FormalBehaviorMetrics
    risk_metrics: FormalRiskMetrics
    profit_metrics: FormalProfitMetrics
    first_evaluation_summary_digest: str
    second_evaluation_summary_digest: str
    deterministic_repeat_match: bool
    terminal_status: str
    terminal_reason_codes: tuple[str, ...]
    round2_precondition_status: str
    round2_instance_created: bool
    result_digest: str
    system_mode: str = "E0_OFFLINE_COUNTERFACTUAL"
    external_execution_authority: str = "NONE_E0"
    executable: bool = False


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _formal_decimal(
    value: Decimal | None,
    code: str,
) -> Decimal:
    if value is None:
        raise FormalExperimentError(code)
    return value


def _metric_digest(value: Mapping[str, object]) -> str:
    return canonical_digest(value)


def _metric_payload(
    value: object,
    *,
    exclude: str = "metrics_digest",
) -> dict[str, object]:
    payload = asdict(value)
    payload.pop(exclude, None)
    return payload


def _build_metrics(
    topology_id: str,
    rows: tuple[PairedObservationReceipt, ...],
) -> tuple[FormalBehaviorMetrics, FormalRiskMetrics, FormalProfitMetrics]:
    hard_errors = sum(item.hard_constraint_error_count for item in rows)
    state_errors = sum(item.state_continuity_error_count for item in rows)
    reproducibility = sum(
        item.reproducibility_difference_count for item in rows
    )
    behavior_payload = {
        "topology_id": topology_id,
        "decision_count": len(rows),
        "mean_dynamic_candidate_coverage": _mean(
            tuple(item.dynamic_candidate_coverage for item in rows)
        ),
        "mean_independent_defect_discovery": _mean(
            tuple(item.material_challenge_coverage for item in rows)
        ),
        "mean_action_quality_score": _mean(
            tuple(item.action_quality_score for item in rows)
        ),
        "hard_constraint_error_count": hard_errors,
        "state_continuity_error_count": state_errors,
        "reproducibility_difference_count": reproducibility,
        "gate_status": (
            "PASS"
            if hard_errors == state_errors == reproducibility == 0
            else "FAIL"
        ),
    }
    behavior = FormalBehaviorMetrics(
        **behavior_payload,
        metrics_digest=_metric_digest(behavior_payload),
    )

    maximum_drawdown = max(
        _formal_decimal(
            item.max_drawdown_fraction,
            "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
        )
        for item in rows
    )
    baseline_drawdown = max(
        _formal_decimal(
            item.frozen_baseline_max_drawdown_fraction,
            "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
        )
        for item in rows
    )
    degradation = maximum_drawdown - baseline_drawdown
    permitted_degradation = max(
        Decimal("0.0025"),
        Decimal("0.25") * baseline_drawdown,
    )
    safety_failures = sum(
        item.safety_state_pit_authority_failures for item in rows
    )
    role_overreach = sum(item.role_overreach_failures for item in rows)
    timeouts = sum(item.timeout_count for item in rows)
    missing_roles = sum(item.missing_role_count for item in rows)
    risk_payload = {
        "topology_id": topology_id,
        "safety_state_pit_authority_failures": safety_failures,
        "role_overreach_failures": role_overreach,
        "timeout_count": timeouts,
        "missing_role_count": missing_roles,
        "max_drawdown_fraction": maximum_drawdown,
        "frozen_baseline_max_drawdown_fraction": baseline_drawdown,
        "drawdown_degradation_fraction": degradation,
        "gate_status": (
            "PASS"
            if (
                safety_failures == 0
                and role_overreach == 0
                and missing_roles == 0
                and maximum_drawdown <= Decimal("0.05")
                and degradation <= permitted_degradation
            )
            else "FAIL"
        ),
    }
    risk = FormalRiskMetrics(
        **risk_payload,
        metrics_digest=_metric_digest(risk_payload),
    )

    net_pnl = sum(
        (
            _formal_decimal(
                item.net_pnl_after_cost,
                "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
            )
            for item in rows
        ),
        Decimal(0),
    )
    baseline_pnl = sum(
        (
            _formal_decimal(
                item.frozen_baseline_net_pnl_after_cost,
                "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
            )
            for item in rows
        ),
        Decimal(0),
    )
    path_capture = _mean(
        tuple(
            _formal_decimal(
                item.primary_path_capture,
                "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
            )
            for item in rows
        )
    )
    baseline_capture = _mean(
        tuple(
            _formal_decimal(
                item.frozen_baseline_primary_path_capture,
                "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
            )
            for item in rows
        )
    )
    profit_payload = {
        "topology_id": topology_id,
        "net_pnl_after_cost": net_pnl,
        "frozen_baseline_net_pnl_after_cost": baseline_pnl,
        "relative_frozen_baseline_pnl": net_pnl - baseline_pnl,
        "transaction_cost": sum(
            (
                _formal_decimal(
                    item.transaction_cost,
                    "FORMAL_ECONOMIC_OBSERVATION_INCOMPLETE",
                )
                for item in rows
            ),
            Decimal(0),
        ),
        "mean_primary_path_capture": path_capture,
        "frozen_baseline_mean_primary_path_capture": baseline_capture,
        "gate_status": (
            "PASS"
            if net_pnl > baseline_pnl and path_capture > baseline_capture
            else "FAIL"
        ),
    }
    profit = FormalProfitMetrics(
        **profit_payload,
        metrics_digest=_metric_digest(profit_payload),
    )
    return behavior, risk, profit


def _validate_receipt_set(
    *,
    contract: FormalExperimentContract,
    dataset: DatasetManifestRef,
    receipts: tuple[PairedObservationReceipt, ...],
    scoring_policy_digest: str,
    cost_policy_digest: str,
    initial_account_digest: str,
    termination_policy_digest: str,
) -> tuple[
    tuple[PairedObservationReceipt, ...],
    tuple[PairedObservationReceipt, ...],
    tuple[PairedObservationReceipt, ...],
]:
    if (
        dataset.quality_verdict != contract.data_quality_required
        or dataset.transport_contract_verdict
        != contract.role_transport_contract_required
        or dataset.transport_schema_digest
        != FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST
    ):
        raise FormalExperimentError(
            "ROLE_INPUT_TRANSPORT_CONTRACT_INVALID"
            if (
                dataset.transport_contract_verdict != "PASS"
                or dataset.transport_schema_digest
                != FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST
            )
            else "DATASET_QUALITY_GATE_NOT_PASS"
        )
    expected_slot_count = (
        len(contract.topology_selection_indices)
        + len(contract.policy_qualification_indices)
        + len(contract.formal_experiment_indices)
    )
    if dataset.decision_slot_count != expected_slot_count:
        raise FormalExperimentError("DATASET_DECISION_SLOT_COUNT_MISMATCH")
    if not receipts:
        raise FormalExperimentError("FORMAL_PAIRED_EVIDENCE_MISSING")
    if any(
        item.transport_schema_digest != dataset.transport_schema_digest
        or item.transport_contract_verdict != "PASS"
        for item in receipts
    ):
        raise FormalExperimentError("ROLE_INPUT_TRANSPORT_CONTRACT_INVALID")
    if any(
        item.dataset_digest != dataset.dataset_digest
        or item.formal_contract_digest != contract.contract_digest
        or item.scoring_policy_digest != scoring_policy_digest
        or item.cost_policy_digest != cost_policy_digest
        or item.initial_account_digest != initial_account_digest
        or item.termination_policy_digest
        != termination_policy_digest
        for item in receipts
    ):
        raise FormalExperimentError(
            "FORMAL_RECEIPT_FROZEN_BINDING_MISMATCH"
        )

    receipt_digests = tuple(item.receipt_digest for item in receipts)
    usage_digests = tuple(item.usage_receipt_digest for item in receipts)
    output_refs = tuple(
        ref for item in receipts for ref in item.raw_output_refs
    )
    if (
        len(set(receipt_digests)) != len(receipt_digests)
        or len(set(usage_digests)) != len(usage_digests)
        or len(set(output_refs)) != len(output_refs)
    ):
        raise FormalExperimentError(
            "FORMAL_EVIDENCE_DUPLICATED_OR_REUSED"
        )
    if (
        {item.requested_model for item in receipts}
        != {contract.requested_model}
        or len({item.model_class for item in receipts}) != 1
        or len({item.parameter_digest for item in receipts}) != 1
        or len({item.budget_limit_digest for item in receipts}) != 1
    ):
        raise FormalExperimentError(
            "FORMAL_MODEL_PARAMETER_BUDGET_NOT_FROZEN"
        )
    served_attestations = {
        item.served_model_attestation
        for item in receipts
        if item.served_model_attestation is not None
    }
    if len(served_attestations) > 1 or (
        served_attestations
        and any(
            item.served_model_attestation is None for item in receipts
        )
    ):
        raise FormalExperimentError(
            "SERVED_MODEL_ATTESTATION_INCONSISTENT"
        )
    if len(
        {item.served_model_attestation_status for item in receipts}
    ) != 1:
        raise FormalExperimentError(
            "SERVED_MODEL_ATTESTATION_STATUS_INCONSISTENT"
        )

    by_key: dict[tuple[str, int, str], PairedObservationReceipt] = {}
    for item in receipts:
        key = (item.sample_cohort, item.sample_index, item.topology_id)
        if key in by_key:
            raise FormalExperimentError("FORMAL_OBSERVATION_DUPLICATE")
        by_key[key] = item

    def rows_for(
        cohort: str,
        indices: tuple[int, ...],
        topology_ids: tuple[str, ...],
    ) -> tuple[PairedObservationReceipt, ...]:
        expected = {
            (cohort, index, topology_id)
            for index in indices
            for topology_id in topology_ids
        }
        actual = {key for key in by_key if key[0] == cohort}
        if actual != expected:
            raise FormalExperimentError(
                f"{cohort}_OBSERVATION_SET_INCOMPLETE"
            )
        return tuple(
            by_key[(cohort, index, topology_id)]
            for index in indices
            for topology_id in topology_ids
        )

    selection = rows_for(
        "TOPOLOGY_SELECTION",
        contract.topology_selection_indices,
        contract.topology_ids,
    )
    expected_sample_keys = {
        ("TOPOLOGY_SELECTION", index)
        for index in contract.topology_selection_indices
    } | {
        ("POLICY_QUALIFICATION", index)
        for index in contract.policy_qualification_indices
    } | {
        ("FORMAL_EXPERIMENT", index)
        for index in contract.formal_experiment_indices
    }
    sample_bindings: dict[
        tuple[str, int],
        tuple[str, str, str],
    ] = {}
    for sample_key in expected_sample_keys:
        paired = tuple(
            item
            for item in receipts
            if (item.sample_cohort, item.sample_index) == sample_key
        )
        if (
            not paired
            or len({item.input_digest for item in paired}) != 1
            or len({item.raw_input_ref for item in paired}) != 1
            or len({item.total_budget_digest for item in paired}) != 1
            or len({item.session_id for item in paired}) != 1
        ):
            raise FormalExperimentError(
                "PAIRED_INPUT_MODEL_BUDGET_MISMATCH"
            )
        sample_bindings[sample_key] = (
            paired[0].input_digest,
            paired[0].raw_input_ref,
            paired[0].session_id,
        )
    if (
        len({value[0] for value in sample_bindings.values()})
        != len(expected_sample_keys)
        or len({value[1] for value in sample_bindings.values()})
        != len(expected_sample_keys)
        or len({value[2] for value in sample_bindings.values()})
        != len(expected_sample_keys)
    ):
        raise FormalExperimentError(
            "FORMAL_DECISION_SAMPLE_REUSED"
        )
    return selection, (), ()


def execute_formal_experiment(
    *,
    offline_run_id: str,
    contract: FormalExperimentContract,
    dataset_manifest_ref: DatasetManifestRef,
    receipts: tuple[PairedObservationReceipt, ...],
    scoring_policy_digest: str,
    cost_policy_digest: str,
    initial_account_digest: str,
    termination_policy_digest: str,
) -> FormalExperimentResult:
    """Evaluate the frozen three-cohort experiment twice and bind one result."""

    _require_run_id(offline_run_id)
    for value, code in (
        (scoring_policy_digest, "SCORING_POLICY_DIGEST_INVALID"),
        (cost_policy_digest, "COST_POLICY_DIGEST_INVALID"),
        (initial_account_digest, "INITIAL_ACCOUNT_DIGEST_INVALID"),
        (termination_policy_digest, "TERMINATION_POLICY_DIGEST_INVALID"),
    ):
        _require_digest(value, code)

    selection, _, _ = _validate_receipt_set(
        contract=contract,
        dataset=dataset_manifest_ref,
        receipts=receipts,
        scoring_policy_digest=scoring_policy_digest,
        cost_policy_digest=cost_policy_digest,
        initial_account_digest=initial_account_digest,
        termination_policy_digest=termination_policy_digest,
    )
    topology = evaluate_agent_topologies(
        tuple(item.to_topology_observation() for item in selection),
        minimum_paired_sessions=contract.minimum_complete_paired_sessions,
        compared_topology_ids=contract.topology_ids,
    )
    if (
        topology.selection_status == "FAIL_INVALID_EXPERIMENT"
        or not topology.equal_input_model_budget_verified
    ):
        raise FormalExperimentError("TOPOLOGY_SELECTION_GATE_FAILED")
    selected_topology = topology.selected_topology_id

    # Qualification and formal cohorts are admitted only after topology is
    # frozen.  They cannot be used to revise that selection.
    by_key = {
        (item.sample_cohort, item.sample_index, item.topology_id): item
        for item in receipts
    }

    def selected_rows(
        cohort: str,
        indices: tuple[int, ...],
    ) -> tuple[PairedObservationReceipt, ...]:
        expected = {
            (cohort, index, selected_topology) for index in indices
        }
        actual = {key for key in by_key if key[0] == cohort}
        if actual != expected:
            raise FormalExperimentError(
                f"{cohort}_OBSERVATION_SET_INCOMPLETE"
            )
        return tuple(
            by_key[(cohort, index, selected_topology)]
            for index in indices
        )

    qualification = selected_rows(
        "POLICY_QUALIFICATION",
        contract.policy_qualification_indices,
    )
    if any(item.qualification_verdict != "PASS" for item in qualification):
        raise FormalExperimentError("POLICY_QUALIFICATION_GATE_NOT_PASS")
    formal_rows = selected_rows(
        "FORMAL_EXPERIMENT",
        contract.formal_experiment_indices,
    )
    if any(
        item.qualification_verdict != "NOT_APPLICABLE"
        for item in formal_rows
    ):
        raise FormalExperimentError(
            "FORMAL_WINDOW_POLICY_REQUALIFICATION_FORBIDDEN"
        )

    behavior, risk, profit = _build_metrics(
        selected_topology,
        formal_rows,
    )
    first_summary_payload = {
        "dataset_digest": dataset_manifest_ref.dataset_digest,
        "experiment_contract_digest": contract.contract_digest,
        "topology_result_digest": topology.result_digest,
        "behavior_metrics_digest": behavior.metrics_digest,
        "risk_metrics_digest": risk.metrics_digest,
        "profit_metrics_digest": profit.metrics_digest,
        "selection_indices": contract.topology_selection_indices,
        "qualification_indices": contract.policy_qualification_indices,
        "formal_indices": contract.formal_experiment_indices,
    }

    # Repeat the actual deterministic evaluation path rather than merely
    # hashing the first summary twice.
    topology_repeat = evaluate_agent_topologies(
        tuple(item.to_topology_observation() for item in selection),
        minimum_paired_sessions=contract.minimum_complete_paired_sessions,
        compared_topology_ids=contract.topology_ids,
    )
    if topology_repeat.selected_topology_id != selected_topology:
        raise FormalExperimentError(
            "FORMAL_EVALUATION_TOPOLOGY_NONDETERMINISTIC"
        )
    qualification_repeat = tuple(
        by_key[("POLICY_QUALIFICATION", index, selected_topology)]
        for index in contract.policy_qualification_indices
    )
    if any(
        item.qualification_verdict != "PASS"
        for item in qualification_repeat
    ):
        raise FormalExperimentError("POLICY_QUALIFICATION_GATE_NOT_PASS")
    formal_rows_repeat = tuple(
        by_key[("FORMAL_EXPERIMENT", index, selected_topology)]
        for index in contract.formal_experiment_indices
    )
    behavior_repeat, risk_repeat, profit_repeat = _build_metrics(
        selected_topology,
        formal_rows_repeat,
    )
    second_summary_payload = {
        "dataset_digest": dataset_manifest_ref.dataset_digest,
        "experiment_contract_digest": contract.contract_digest,
        "topology_result_digest": topology_repeat.result_digest,
        "behavior_metrics_digest": behavior_repeat.metrics_digest,
        "risk_metrics_digest": risk_repeat.metrics_digest,
        "profit_metrics_digest": profit_repeat.metrics_digest,
        "selection_indices": contract.topology_selection_indices,
        "qualification_indices": contract.policy_qualification_indices,
        "formal_indices": contract.formal_experiment_indices,
    }
    first_summary_digest = canonical_digest(first_summary_payload)
    second_summary_digest = canonical_digest(second_summary_payload)
    deterministic_repeat_match = (
        first_summary_digest == second_summary_digest
    )
    if not deterministic_repeat_match:
        raise FormalExperimentError(
            "FORMAL_EVALUATION_DIGEST_NONDETERMINISTIC"
        )

    reasons: list[str] = []
    if behavior.gate_status != "PASS":
        reasons.append("FORMAL_BEHAVIOR_GATE_FAILED")
    if risk.gate_status != "PASS":
        reasons.append("FORMAL_RISK_GATE_FAILED")
    if profit.gate_status != "PASS":
        reasons.append("FORMAL_ECONOMIC_GATE_FAILED")
    all_gates_pass = not reasons
    terminal_status = (
        "PASS_FORMAL_E0"
        if all_gates_pass
        else "FAIL_REPAIR_AND_RESTART_FORMAL_E0"
    )
    round2_status = (
        "PASS_SEPARATE_101_GATE_ELIGIBLE"
        if all_gates_pass
        else "BLOCKED_NOT_CREATED"
    )

    ordered_receipts = tuple(
        sorted(
            receipts,
            key=lambda item: (
                _COHORTS.index(item.sample_cohort),
                item.sample_index,
                item.topology_id,
            ),
        )
    )
    receipt_set_digest = canonical_digest(
        tuple(item.receipt_digest for item in ordered_receipts)
    )
    served_model_attestation = ordered_receipts[
        0
    ].served_model_attestation
    served_model_attestation_status = ordered_receipts[
        0
    ].served_model_attestation_status
    authority_payload = {
        "schema_id": "authority_snapshot",
        "schema_version": "1.0.0",
        "record_id": f"{offline_run_id}:formal-e0-authority",
        "revision": 1,
        "value_refs": [
            f"dataset-id:{dataset_manifest_ref.dataset_id}",
            f"dataset-digest:{dataset_manifest_ref.dataset_digest}",
            f"experiment-contract-digest:{contract.contract_digest}",
            (
                "role-input-transport-schema-digest:"
                f"{dataset_manifest_ref.transport_schema_digest}"
            ),
            f"paired-receipt-set-digest:{receipt_set_digest}",
            f"requested-model:{contract.requested_model}",
            (
                "served-model-attestation:"
                + (
                    served_model_attestation
                    if served_model_attestation is not None
                    else "UNKNOWN_NOT_EXPOSED"
                )
            ),
            (
                "served-model-attestation-status:"
                f"{served_model_attestation_status}"
            ),
            (
                "model-call-monetary-cost:"
                + (
                    "IDENTIFIED"
                    if all(
                        item.cost_microunits is not None
                        for item in ordered_receipts
                    )
                    else "UNKNOWN_NOT_EXPOSED"
                )
            ),
            "paper-action-authority:NONE",
            "live-action-authority:NONE",
            "second-round-instance-authority:SEPARATE_GATE_ONLY",
        ],
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    authority_snapshot = dict(authority_payload)
    authority_snapshot["record_digest"] = canonical_digest(authority_payload)

    manifest_payload = {
        "schema_id": "project_bootstrap_manifest",
        "schema_version": "1.0.0",
        "manifest_id": offline_run_id,
        "manifest_version": "1.0.0",
        "entry_refs": [
            f"dataset-id:{dataset_manifest_ref.dataset_id}",
            f"dataset-digest:{dataset_manifest_ref.dataset_digest}",
            f"experiment-contract-digest:{contract.contract_digest}",
            f"receipt-set-digest:{receipt_set_digest}",
            f"scoring-policy-digest:{scoring_policy_digest}",
            f"cost-policy-digest:{cost_policy_digest}",
            f"initial-account-digest:{initial_account_digest}",
            f"termination-policy-digest:{termination_policy_digest}",
            f"requested-model:{contract.requested_model}",
            (
                "served-model-attestation:"
                + (
                    served_model_attestation
                    if served_model_attestation is not None
                    else "UNKNOWN_NOT_EXPOSED"
                )
            ),
            (
                "served-model-attestation-status:"
                f"{served_model_attestation_status}"
            ),
            (
                "model-call-monetary-cost:"
                + (
                    "IDENTIFIED"
                    if all(
                        item.cost_microunits is not None
                        for item in ordered_receipts
                    )
                    else "UNKNOWN_NOT_EXPOSED"
                )
            ),
            f"parameter-digest:{ordered_receipts[0].parameter_digest}",
            f"budget-limit-digest:{ordered_receipts[0].budget_limit_digest}",
            f"selected-topology:{selected_topology}",
            "topology-selection-indices:96-127",
            "policy-qualification-indices:128-159",
            "formal-experiment-indices:160-191",
            "second-round-101-instance:NOT_CREATED",
        ],
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    experiment_manifest = dict(manifest_payload)
    experiment_manifest["manifest_digest"] = canonical_digest(manifest_payload)

    result_payload = {
        "offline_run_id": offline_run_id,
        "dataset_manifest_ref": asdict(dataset_manifest_ref),
        "experiment_contract_digest": contract.contract_digest,
        "receipt_count": len(receipts),
        "topology_selection_session_count": len(
            contract.topology_selection_indices
        ),
        "policy_qualification_session_count": len(
            contract.policy_qualification_indices
        ),
        "formal_experiment_session_count": len(
            contract.formal_experiment_indices
        ),
        "authority_snapshot": authority_snapshot,
        "experiment_manifest": experiment_manifest,
        "topology_evaluation": asdict(topology),
        "behavior_metrics": asdict(behavior),
        "risk_metrics": asdict(risk),
        "profit_metrics": asdict(profit),
        "first_evaluation_summary_digest": first_summary_digest,
        "second_evaluation_summary_digest": second_summary_digest,
        "deterministic_repeat_match": deterministic_repeat_match,
        "terminal_status": terminal_status,
        "terminal_reason_codes": tuple(reasons),
        "round2_precondition_status": round2_status,
        "round2_instance_created": False,
        "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
        "external_execution_authority": "NONE_E0",
        "executable": False,
    }
    return FormalExperimentResult(
        offline_run_id=offline_run_id,
        dataset_manifest_ref=dataset_manifest_ref,
        experiment_contract_digest=contract.contract_digest,
        receipt_count=len(receipts),
        topology_selection_session_count=len(
            contract.topology_selection_indices
        ),
        policy_qualification_session_count=len(
            contract.policy_qualification_indices
        ),
        formal_experiment_session_count=len(
            contract.formal_experiment_indices
        ),
        authority_snapshot=authority_snapshot,
        experiment_manifest=experiment_manifest,
        topology_evaluation=topology,
        behavior_metrics=behavior,
        risk_metrics=risk,
        profit_metrics=profit,
        first_evaluation_summary_digest=first_summary_digest,
        second_evaluation_summary_digest=second_summary_digest,
        deterministic_repeat_match=deterministic_repeat_match,
        terminal_status=terminal_status,
        terminal_reason_codes=tuple(reasons),
        round2_precondition_status=round2_status,
        round2_instance_created=False,
        result_digest=canonical_digest(result_payload),
    )


__all__ = [
    "DatasetManifestRef",
    "FormalBehaviorMetrics",
    "FORMAL_E0_CONTRACT_DIGEST",
    "FORMAL_E0_ROLE_INPUT_TRANSPORT_SCHEMA_DIGEST",
    "FormalExperimentContract",
    "FormalExperimentError",
    "FormalExperimentResult",
    "FormalProfitMetrics",
    "FormalRiskMetrics",
    "PairedObservationReceipt",
    "build_paired_observation_receipt",
    "execute_formal_experiment",
]
