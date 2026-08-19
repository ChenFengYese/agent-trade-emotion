"""Frozen, non-executable V3.1 experiment and outcome contracts.

This module owns only deterministic domain documents.  It does not create a
manifest, schedule a monitor, collect market data, mutate a portfolio, or
authorize paper/live execution.  Application and infrastructure code must bind
these contracts before a fresh experiment can be called run-ready.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    CanonicalContractError,
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)
from .association_estimation import (
    AssociationEstimationError,
    verify_pearson_association_receipt,
)


APPROVED_THEORY_SHA256 = (
    "ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553"
)
EXPERIMENT_SCHEMA_ID = "theory_paper_v2_v31_minimal_experiment_contract"
MONITOR_SCHEMA_ID = "theory_paper_v2_v31_typed_path_monitor_plan"
OUTCOME_SCHEMA_ID = "theory_paper_v2_v31_path_outcome_receipt"
SCHEMA_VERSION = "1.0.0"
OUTCOME_HORIZON = timedelta(hours=1)
OUTCOME_GRACE = timedelta(minutes=15)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class V31ExperimentContractError(ValueError):
    """A frozen experiment or outcome contract failed closed."""


class MonitorOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    EXISTS = "EXISTS"


class MonitorRuleRole(StrEnum):
    CONFIRMATION = "CONFIRMATION"
    CONTRADICTION = "CONTRADICTION"
    FALSIFIER = "FALSIFIER"


class RuleTruth(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class ObservationMissingness(StrEnum):
    OBSERVED = "OBSERVED"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class ObservationQuality(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ExpectationOutcome(StrEnum):
    FULFILLED = "FULFILLED"
    PARTIAL = "PARTIAL"
    FALSIFIED = "FALSIFIED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class PathOutcome(StrEnum):
    SUPPORTED = "SUPPORTED"
    FALSIFIED = "FALSIFIED"
    UNRESOLVED = "UNRESOLVED"
    OTHER = "OTHER"


_QUALITY_RANK = {
    ObservationQuality.UNKNOWN: 0,
    ObservationQuality.LOW: 1,
    ObservationQuality.MEDIUM: 2,
    ObservationQuality.HIGH: 3,
}


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31ExperimentContractError(code)
    return value.strip()


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31ExperimentContractError(code)
    return value


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31ExperimentContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31ExperimentContractError(code) from exc
    if parsed.tzinfo is None:
        raise V31ExperimentContractError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, (float, bool)):
        raise V31ExperimentContractError(code)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V31ExperimentContractError(code) from exc
    if not parsed.is_finite():
        raise V31ExperimentContractError(code)
    return parsed


def _canonical_value(value: Any, code: str) -> Any:
    try:
        if isinstance(value, Decimal):
            return canonical_decimal(value)
        canonical_digest(value)
    except CanonicalContractError as exc:
        raise V31ExperimentContractError(code) from exc
    return value


def _authority_boundary() -> dict[str, Any]:
    return {
        "data_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


def _capability_matrix() -> list[dict[str, Any]]:
    implemented = "IMPLEMENTED_AND_VERIFIED"
    excluded = "EXCLUDED_NO_CLAIM"
    local = "LOCAL_DOMAIN_CONTRACT_ONLY"
    return [
        {
            "capability_id": "PIT_REVISION_AND_EXACT_EVIDENCE_BINDING",
            "status": implemented,
            "used_or_evaluated": True,
            "evidence_scope": local,
        },
        {
            "capability_id": "SINGLE_PREREGISTERED_PEARSON_BASELINE",
            "status": implemented,
            "used_or_evaluated": True,
            "evidence_scope": local,
        },
        {
            "capability_id": "TYPED_PATH_MONITOR_PLAN_AND_OUTCOME_RECEIPT",
            "status": implemented,
            "used_or_evaluated": True,
            "evidence_scope": local,
        },
        {
            "capability_id": "ACTUAL_MULTIPLICITY_AND_INDEPENDENT_CAUSAL_VALIDATION",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "DCC_GRANGER_TAIL_SPILLOVER_EVENT_WINDOW",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "GENERAL_CREDAL_ENSEMBLE_POSTERIOR_MODE_PROMOTION",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "NATIVE_TWELVE_AXIS_SOURCES_AND_FULL_GRAPH_PROJECTION",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "PARTIAL_OR_CYCLIC_PATH_EXECUTION",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "DURABLE_CROSS_CYCLE_MONITOR_RUNTIME",
            "status": implemented,
            "used_or_evaluated": True,
            "evidence_scope": "LOCAL_DURABLE_RUNTIME",
        },
        {
            "capability_id": "PAYOFF_UTILITY_SCENARIO_COST_NUMERIC_EV_OR_REGRET",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
        {
            "capability_id": "PORTFOLIO_MUTATION_GEOMETRY_OR_REENTRY_REDUCER",
            "status": excluded,
            "used_or_evaluated": False,
            "evidence_scope": "NO_CLAIM",
        },
    ]


def _financial_shadow_scope() -> dict[str, Any]:
    """Return the sole preregistered non-account financial comparison scope."""

    return {
        "mode": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
        "initial_shadow_account": {
            "equity_usdt": "10000",
            "margin_used_usdt": "0",
            "margin_available_usdt": "10000",
            "max_gross_leverage": "2",
            "target_position": "FLAT",
            "other_lots": [],
            "pending_orders": [],
        },
        "risk_policy": {
            "fee_rate": "0.001",
            "slippage_rate": "0.002",
            "initial_margin_rate": "0.5",
            "max_gross_leverage": "2",
            "portfolio_risk_cap_usdt": "300",
            "symbol_risk_cap_usdt": "100",
            "gross_notional_cap_usdt": "2000",
            "symbol_notional_cap_usdt": "1000",
        },
        "candidate_grid": {
            "position_side": "FLAT",
            "entry_scale_grid_pct": [25],
            "partial_exit_scale_grid_pct": [40],
            "allowed_entry_roles": ["TACTICAL"],
            "legal_candidate_count": 3,
            "legal_action_classes": ["OPEN_LONG", "OPEN_SHORT", "WAIT"],
        },
        "market_economics_policy": {
            "instrument_id": "BTC-USDT-SWAP",
            "mark_price_source": "OKX_PUBLIC_MARK_PRICE_PIT",
            "contract_specification_source": "OKX_PUBLIC_INSTRUMENT_PIT",
            "contract_multiplier": "0.01",
            "contract_multiplier_unit": "BTC_PER_CONTRACT",
            "contract_size_multiplier": "1",
            "quantity_step_contracts": "0.01",
            "minimum_quantity_contracts": "0.01",
            "price_tick_usdt": "0.1",
            "long_protective_stop_multiplier": "0.98",
            "short_protective_stop_multiplier": "1.02",
            "protective_stop_rounding": "OUTWARD_TO_PUBLIC_PRICE_TICK",
            "quantity_rounding": "DOWN_TO_PUBLIC_QUANTITY_STEP",
            "minimum_quantity_result": "INFEASIBLE_NOT_ROUNDED_UP",
            "funding_cost_policy": (
                "UNKNOWN_UNLESS_SETTLEMENT_WINDOW_AND_RATE_ARE_PIT_BOUND"
            ),
            "funding_cost_included": False,
        },
        "cost_assumption_status": (
            "PREREGISTERED_CONSERVATIVE_RESEARCH_ASSUMPTION_NOT_ACCOUNT_TIER"
        ),
        "payoff_matrix_status": "ABSENT_NO_NUMERIC_EV_OR_REGRET",
        "mid_run_financial_assumption_change_forbidden": True,
    }


def build_minimal_experiment_contract(
    *, contract_id: str, run_id: str, frozen_at: str
) -> dict[str, Any]:
    """Build the one allowed contract-only V3.1 experiment scope."""

    document = {
        "schema_id": EXPERIMENT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "contract_id": _text(contract_id, "EXPERIMENT_CONTRACT_ID_INVALID"),
        "run_id": _text(run_id, "EXPERIMENT_RUN_ID_INVALID"),
        "frozen_at": _time_text(_time(frozen_at, "EXPERIMENT_FROZEN_AT_INVALID")),
        "approved_theory_sha256": APPROVED_THEORY_SHA256,
        "readiness_status": "CONTRACT_ONLY_NOT_RUN_READY",
        "instrument": {
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "market_type": "PERPETUAL_SWAP",
            "spot_claim": False,
        },
        "cycle_protocol": {
            "accepted_cycle_count": 8,
            "timeframe": "1H",
            "bar_state": "CLOSED_ONLY",
            "one_new_distinct_bar_per_cycle": True,
            "duplicate_as_of_forbidden": True,
            "outcome_horizon": "1H",
            "outcome_horizon_seconds": 3600,
            "outcome_grace_seconds": 900,
            "mid_run_rule_change_forbidden": True,
        },
        "portfolio_scope": {
            "mode": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
            "initial_position": "FLAT",
            "legal_research_labels": ["OPEN_LONG", "OPEN_SHORT", "WAIT"],
            "selection_is_non_executable_label": True,
            "next_cycle_portfolio_writeback": False,
            "portfolio_performance_claim": False,
            "financial_shadow": _financial_shadow_scope(),
        },
        "association_scope": {
            "use": "DESCRIPTIVE_END_OF_RUN_DIAGNOSTIC_ONLY",
            "action_or_probability_input": False,
            "association_claim_only": True,
            "causal_claim": False,
            "pair_universe": [
                {
                    "pair_id": "OKX:BTC-USDT-SWAP:1H_RETURN__VOLUME_VS_20BAR_MEDIAN",
                    "source_metric": "candle-1h-return-pct",
                    "source_node_id": "metric:candle-1h-return-pct",
                    "source_transform": "CURRENT_CLOSED_1H_RETURN_PERCENT_V1",
                    "target_metric": "candle-1h-volume-vs-20bar-median",
                    "target_node_id": "metric:candle-1h-volume-vs-20bar-median",
                    "target_transform": "CURRENT_CLOSED_1H_VOLUME_DIV_20BAR_MEDIAN_V1",
                    "timeframe": "1H",
                    "lag": {"value": 0, "unit": "1H", "direction": "SYNCHRONOUS"},
                }
            ],
            "candidate_pair_count": 1,
            "candidate_search": "FORBIDDEN",
            "estimator": "PEARSON_PAIRWISE_COMPLETE_FISHER_Z_95_V1",
            "model_version": "V3_1_PEARSON_BASELINE_1_0_0",
            "window": {
                "selection": "LAST_8_DISTINCT_COMPLETE_CLOSED_1H_PAIRS_BEFORE_DECISION",
                "sample_count": 8,
                "imputation": "FORBIDDEN",
                "zero_variance_result": "UNKNOWN_NO_RECEIPT",
                "insufficient_sample_result": "UNKNOWN_NO_RECEIPT",
            },
            "multiplicity": {
                "family_size": 1,
                "policy": "SINGLE_PRE_REGISTERED_PAIR_FAMILY_SIZE_1_NO_CORRECTION",
                "correction_applied": False,
            },
            "association_change_claim": False,
        },
        "evaluation": {
            "primary_endpoints": [
                "EIGHT_ACCEPTED_CYCLES_OR_EXPLICIT_FAILURE_CLOSE",
                "CONTRACT_AND_DIGEST_FIDELITY",
                "NO_AUTHORITY_EXPANSION",
            ],
            "secondary_endpoints": [
                "CATEGORICAL_1H_EXPECTATION_AND_PATH_RESOLUTION",
                "FALSIFIER_HIT_COUNT",
                "HYPOTHESIS_CONTINUITY_NOVELTY_AND_DEDUPLICATION",
                "ASSOCIATION_DIAGNOSTIC_IF_EXACTLY_8_VALID_PAIRS",
            ],
            "excluded_metrics_and_claims": [
                "PROFITABILITY",
                "CALIBRATED_PROBABILITY",
                "BRIER_LOG_ECE",
                "AGENT_SUPERIORITY",
                "CAUSALITY",
                "EV_OR_REGRET",
                "PORTFOLIO_PERFORMANCE",
                "CROSS_MARKET_OR_CROSS_REGIME_GENERALIZATION",
            ],
            "baseline": {
                "wait_reference": "NON_SCORING_CONTEXT_ONLY",
                "prior_lead_persistence": "DESCRIPTIVE_ONLY",
                "agent_incremental_superiority": "UNKNOWN",
            },
            "unknown_other_policy": {
                "OTHER": "LEGITIMATE_RESIDUAL_OUTCOME",
                "UNKNOWN": "NEVER_FALSE_ZERO_OR_IMPUTED",
                "unknown_in_hit_denominator": False,
                "unknown_counted_as_coverage_loss": True,
                "missing_source_and_unresolved_hypothesis_separated": True,
            },
            "stop_rules": {
                "action": "STOP_WITHOUT_RETRY_REPAIR_SHORTENING_OR_RULE_CHANGE",
                "stop_immediately_on": [
                    "AUTHORITY_EXPANSION",
                    "CONTRACT_OR_DIGEST_DRIFT",
                    "DUPLICATE_OR_NON_CLOSED_1H_BAR",
                    "FUTURE_OR_NON_PIT_DATA",
                    "OUTCOME_READ_BEFORE_NOT_BEFORE",
                    "OUTCOME_RECEIPT_CHAIN_BREAK",
                    "REQUIRED_PUBLIC_SOURCE_UNAVAILABLE",
                    "UNKNOWN_COERCED_TO_VALUE",
                ],
                "failure_taxonomy": [
                    "CONTRACT_FAILURE",
                    "DATA_FAILURE",
                    "AGENT_FAILURE",
                    "MONITOR_FAILURE",
                    "STORE_FAILURE",
                    "EXTERNAL_LIMITATION",
                ],
            },
        },
        "capability_matrix": _capability_matrix(),
        "authority_boundary": _authority_boundary(),
        "limitations": [
            "Domain contracts and tests do not constitute a manifest or runtime.",
            "The exact instrument is OKX BTC-USDT-SWAP, not BTC-USDT spot.",
            "All excluded capabilities remain UNKNOWN and support no claim.",
        ],
    }
    return self_digest(document, "experiment_contract_digest")


def verify_minimal_experiment_contract(contract: Mapping[str, Any]) -> str:
    """Reject any semantic or digest drift from the frozen minimal scope."""

    if not isinstance(contract, Mapping):
        raise V31ExperimentContractError("EXPERIMENT_CONTRACT_INVALID")
    try:
        supplied = verify_self_digest(contract, "experiment_contract_digest")
        rebuilt = build_minimal_experiment_contract(
            contract_id=contract["contract_id"],
            run_id=contract["run_id"],
            frozen_at=contract["frozen_at"],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentContractError):
            raise
        raise V31ExperimentContractError("EXPERIMENT_CONTRACT_INVALID") from exc
    if rebuilt != dict(contract) or supplied != rebuilt["experiment_contract_digest"]:
        raise V31ExperimentContractError("EXPERIMENT_CONTRACT_RECONSTRUCTION_MISMATCH")
    return supplied


@dataclass(frozen=True, slots=True)
class ClosedHourCycleBinding:
    """The association-visible projection of one accepted closed-hour cycle."""

    cycle_index: int
    cycle_id: str
    pair_universe_id: str
    pair_id: str
    bar_as_of: str
    pair_available_at: str
    source_datum_digest: str
    target_datum_digest: str
    accepted_state_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.cycle_index, bool)
            or not isinstance(self.cycle_index, int)
            or not 1 <= self.cycle_index <= 8
        ):
            raise V31ExperimentContractError("CYCLE_BINDING_INDEX_INVALID")
        _text(self.cycle_id, "CYCLE_BINDING_ID_INVALID")
        _text(
            self.pair_universe_id,
            "CYCLE_BINDING_PAIR_UNIVERSE_ID_INVALID",
        )
        _text(self.pair_id, "CYCLE_BINDING_PAIR_ID_INVALID")
        as_of = _time(self.bar_as_of, "CYCLE_BINDING_TIME_INVALID")
        available = _time(self.pair_available_at, "CYCLE_BINDING_TIME_INVALID")
        if as_of.minute or as_of.second or as_of.microsecond:
            raise V31ExperimentContractError("CYCLE_BINDING_BAR_NOT_CLOSED_1H_BOUNDARY")
        # OKX candle timestamps identify the opening boundary.  A 1H sample is
        # closed-only only after the following hourly boundary is available.
        if available < as_of + timedelta(hours=1):
            raise V31ExperimentContractError("CYCLE_BINDING_NOT_POINT_IN_TIME")
        for value in (
            self.source_datum_digest,
            self.target_datum_digest,
            self.accepted_state_digest,
        ):
            _digest(value, "CYCLE_BINDING_DIGEST_INVALID")

    def to_document(self) -> dict[str, Any]:
        return {
            "cycle_index": self.cycle_index,
            "cycle_id": self.cycle_id,
            "pair_universe_id": self.pair_universe_id,
            "pair_id": self.pair_id,
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "timeframe": "1H",
            "bar_state": "CLOSED_ONLY",
            "bar_as_of": _time_text(_time(self.bar_as_of, "CYCLE_BINDING_TIME_INVALID")),
            "pair_available_at": _time_text(
                _time(self.pair_available_at, "CYCLE_BINDING_TIME_INVALID")
            ),
            "source_datum_digest": self.source_datum_digest,
            "target_datum_digest": self.target_datum_digest,
            "accepted_state_digest": self.accepted_state_digest,
        }


def verify_eight_closed_hour_cycles(
    *,
    experiment_contract: Mapping[str, Any],
    cycles: Sequence[ClosedHourCycleBinding],
    completed_at: str,
) -> str:
    """Verify exactly eight distinct, increasing, closed 1H accepted cycles."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    if isinstance(cycles, (str, bytes)):
        raise V31ExperimentContractError("CYCLE_BINDINGS_INVALID")
    rows = tuple(cycles)
    if len(rows) != 8 or any(not isinstance(row, ClosedHourCycleBinding) for row in rows):
        raise V31ExperimentContractError("CYCLE_BINDINGS_EXACTLY_EIGHT_REQUIRED")
    if tuple(row.cycle_index for row in rows) != tuple(range(1, 9)):
        raise V31ExperimentContractError("CYCLE_BINDING_INDEX_SEQUENCE_INVALID")
    if len({row.cycle_id for row in rows}) != 8 or len({row.pair_id for row in rows}) != 8:
        raise V31ExperimentContractError("CYCLE_BINDING_ID_DUPLICATE")
    expected_pair_universe_id = experiment_contract["association_scope"][
        "pair_universe"
    ][0]["pair_id"]
    if any(
        row.pair_universe_id != expected_pair_universe_id for row in rows
    ):
        raise V31ExperimentContractError(
            "CYCLE_BINDING_PAIR_UNIVERSE_MISMATCH"
        )
    as_of_values = tuple(_time(row.bar_as_of, "CYCLE_BINDING_TIME_INVALID") for row in rows)
    if (
        len(set(as_of_values)) != 8
        or tuple(sorted(as_of_values)) != as_of_values
        or any(
            current - previous != timedelta(hours=1)
            for previous, current in zip(as_of_values, as_of_values[1:])
        )
    ):
        raise V31ExperimentContractError("CYCLE_BINDING_BAR_SEQUENCE_INVALID")
    completion = _time(completed_at, "CYCLE_BINDING_COMPLETED_AT_INVALID")
    if any(
        _time(row.pair_available_at, "CYCLE_BINDING_TIME_INVALID") > completion
        for row in rows
    ):
        raise V31ExperimentContractError("CYCLE_BINDING_FUTURE_DATA_FORBIDDEN")
    return canonical_digest(
        {
            "schema_id": "theory_paper_v2_v31_closed_hour_cycle_sequence",
            "schema_version": SCHEMA_VERSION,
            "experiment_contract_digest": contract_digest,
            "completed_at": _time_text(completion),
            "cycles": [row.to_document() for row in rows],
            "authority_boundary": _authority_boundary(),
        }
    )


def verify_frozen_association_receipt(
    *,
    experiment_contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
    accepted_cycles: Sequence[ClosedHourCycleBinding],
) -> str:
    """Return a digest binding the only Pearson receipt to eight accepted cycles."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    if not isinstance(receipt, Mapping):
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_RECEIPT_INVALID")
    try:
        receipt_digest = verify_pearson_association_receipt(receipt)
    except (AssociationEstimationError, TypeError, ValueError) as exc:
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_RECEIPT_INVALID") from exc
    scope = experiment_contract["association_scope"]
    pair_scope = scope["pair_universe"][0]
    expected_fields = {
        "source_node_id": pair_scope["source_node_id"],
        "target_node_id": pair_scope["target_node_id"],
        "timeframe": "1H",
        "method": scope["estimator"],
        "model_version": scope["model_version"],
        "sample_count": 8,
        "multiple_testing_control": scope["multiplicity"]["policy"],
        "interpretation_boundary": "ASSOCIATIONAL_NOT_CAUSAL",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    if any(receipt.get(key) != value for key, value in expected_fields.items()):
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_SCOPE_MISMATCH")
    rows = tuple(accepted_cycles)
    sequence_digest = verify_eight_closed_hour_cycles(
        experiment_contract=experiment_contract,
        cycles=rows,
        completed_at=receipt["decision_at"],
    )
    paired = receipt.get("paired_observations")
    if not isinstance(paired, list) or len(paired) != 8:
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_PAIR_COUNT_MISMATCH")
    pairs_by_id = {row.get("pair_id"): row for row in paired if isinstance(row, Mapping)}
    if len(pairs_by_id) != 8:
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_PAIR_IDS_INVALID")
    for cycle in rows:
        pair = pairs_by_id.get(cycle.pair_id)
        if pair is None or any(
            pair.get(key) != expected
            for key, expected in {
                "as_of": _time_text(_time(cycle.bar_as_of, "CYCLE_BINDING_TIME_INVALID")),
                "available_at": _time_text(
                    _time(cycle.pair_available_at, "CYCLE_BINDING_TIME_INVALID")
                ),
                "source_datum_digest": cycle.source_datum_digest,
                "target_datum_digest": cycle.target_datum_digest,
            }.items()
        ):
            raise V31ExperimentContractError("FROZEN_ASSOCIATION_CYCLE_BINDING_MISMATCH")
    if receipt["window_start"] != _time_text(
        _time(rows[0].bar_as_of, "CYCLE_BINDING_TIME_INVALID")
    ) or receipt["window_end"] != _time_text(
        _time(rows[-1].bar_as_of, "CYCLE_BINDING_TIME_INVALID")
    ):
        raise V31ExperimentContractError("FROZEN_ASSOCIATION_WINDOW_MISMATCH")
    return canonical_digest(
        {
            "experiment_contract_digest": contract_digest,
            "cycle_sequence_digest": sequence_digest,
            "association_estimation_receipt_digest": receipt_digest,
            "lag": pair_scope["lag"],
            "use": scope["use"],
        }
    )


@dataclass(frozen=True, slots=True)
class FrozenMonitorRule:
    rule_id: str
    role: MonitorRuleRole
    observable_ref: str
    operator: MonitorOperator
    expected: Any
    unit: str
    timeframe: str = "1H"

    def __post_init__(self) -> None:
        _text(self.rule_id, "MONITOR_RULE_ID_INVALID")
        _text(self.observable_ref, "MONITOR_RULE_OBSERVABLE_INVALID")
        _text(self.unit, "MONITOR_RULE_UNIT_INVALID")
        if not isinstance(self.role, MonitorRuleRole) or not isinstance(
            self.operator, MonitorOperator
        ):
            raise V31ExperimentContractError("MONITOR_RULE_ENUM_INVALID")
        if self.timeframe != "1H":
            raise V31ExperimentContractError("MONITOR_RULE_TIMEFRAME_NOT_FROZEN")
        if self.operator is MonitorOperator.EXISTS:
            if self.expected is not None:
                raise V31ExperimentContractError("MONITOR_EXISTS_EXPECTED_MUST_BE_NULL")
        elif self.expected is None:
            raise V31ExperimentContractError("MONITOR_RULE_EXPECTED_REQUIRED")
        if self.operator is MonitorOperator.IN and (
            not isinstance(self.expected, (list, tuple)) or not self.expected
        ):
            raise V31ExperimentContractError("MONITOR_IN_EXPECTED_COLLECTION_REQUIRED")
        _canonical_value(self.expected, "MONITOR_RULE_EXPECTED_INVALID")

    def to_document(self) -> dict[str, Any]:
        expected = _canonical_value(self.expected, "MONITOR_RULE_EXPECTED_INVALID")
        return {
            "rule_id": self.rule_id,
            "role": self.role.value,
            "observable_ref": self.observable_ref,
            "operator": self.operator.value,
            "expected": expected,
            "unit": self.unit,
            "timeframe": self.timeframe,
        }


@dataclass(frozen=True, slots=True)
class OutcomeObservation:
    observable_ref: str
    value: Any
    as_of: str
    available_at: str
    missingness: ObservationMissingness
    quality: ObservationQuality
    coverage: Decimal | str
    conflict_state: str
    source_request_id: str
    source_record_digest: str
    raw_capture_digest: str
    datum_digest: str

    def __post_init__(self) -> None:
        _text(self.observable_ref, "OUTCOME_OBSERVABLE_REF_INVALID")
        as_of = _time(self.as_of, "OUTCOME_OBSERVATION_TIME_INVALID")
        available = _time(self.available_at, "OUTCOME_OBSERVATION_TIME_INVALID")
        if as_of > available:
            raise V31ExperimentContractError("OUTCOME_OBSERVATION_NOT_POINT_IN_TIME")
        if not isinstance(self.missingness, ObservationMissingness) or not isinstance(
            self.quality, ObservationQuality
        ):
            raise V31ExperimentContractError("OUTCOME_OBSERVATION_ENUM_INVALID")
        coverage = _decimal(self.coverage, "OUTCOME_COVERAGE_INVALID")
        if coverage < 0 or coverage > 1:
            raise V31ExperimentContractError("OUTCOME_COVERAGE_INVALID")
        object.__setattr__(self, "coverage", coverage)
        _text(self.conflict_state, "OUTCOME_CONFLICT_STATE_INVALID")
        _text(self.source_request_id, "OUTCOME_SOURCE_REQUEST_ID_INVALID")
        for value in (
            self.source_record_digest,
            self.raw_capture_digest,
            self.datum_digest,
        ):
            _digest(value, "OUTCOME_SOURCE_DIGEST_INVALID")
        if self.missingness is ObservationMissingness.OBSERVED:
            if self.value is None:
                raise V31ExperimentContractError("OUTCOME_OBSERVED_VALUE_REQUIRED")
            _canonical_value(self.value, "OUTCOME_VALUE_INVALID")
        elif self.value is not None:
            raise V31ExperimentContractError("OUTCOME_UNKNOWN_VALUE_IMPUTATION_FORBIDDEN")

    def to_document(self) -> dict[str, Any]:
        document = {
            "observable_ref": self.observable_ref,
            "value": _canonical_value(self.value, "OUTCOME_VALUE_INVALID"),
            "as_of": _time_text(_time(self.as_of, "OUTCOME_OBSERVATION_TIME_INVALID")),
            "available_at": _time_text(
                _time(self.available_at, "OUTCOME_OBSERVATION_TIME_INVALID")
            ),
            "missingness": self.missingness.value,
            "quality": self.quality.value,
            "coverage": canonical_decimal(self.coverage),
            "conflict_state": self.conflict_state,
            "source_request_id": self.source_request_id,
            "source_record_digest": self.source_record_digest,
            "raw_capture_digest": self.raw_capture_digest,
            "datum_digest": self.datum_digest,
        }
        return self_digest(document, "observation_digest")


_ORIGIN_KEYS = (
    "accepted_state",
    "path_set",
    "path",
    "hypothesis_revision",
    "expectation_revision",
)


def _origin_bindings(value: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != set(_ORIGIN_KEYS):
        raise V31ExperimentContractError("MONITOR_ORIGIN_BINDINGS_INVALID")
    result: dict[str, dict[str, str]] = {}
    for key in _ORIGIN_KEYS:
        binding = value[key]
        if not isinstance(binding, Mapping) or set(binding) != {"ref", "digest"}:
            raise V31ExperimentContractError("MONITOR_ORIGIN_BINDING_INVALID")
        result[key] = {
            "ref": _text(binding["ref"], "MONITOR_ORIGIN_REF_INVALID"),
            "digest": _digest(binding["digest"], "MONITOR_ORIGIN_DIGEST_INVALID"),
        }
    return result


def _rules(
    value: Sequence[FrozenMonitorRule], observable_ref: str
) -> tuple[FrozenMonitorRule, ...]:
    if isinstance(value, (str, bytes)):
        raise V31ExperimentContractError("MONITOR_RULES_INVALID")
    rules = tuple(value)
    if len(rules) != 3 or any(not isinstance(rule, FrozenMonitorRule) for rule in rules):
        raise V31ExperimentContractError("MONITOR_RULES_EXACTLY_THREE_REQUIRED")
    if {rule.role for rule in rules} != set(MonitorRuleRole):
        raise V31ExperimentContractError("MONITOR_RULE_ROLES_INCOMPLETE")
    if len({rule.rule_id for rule in rules}) != 3:
        raise V31ExperimentContractError("MONITOR_RULE_IDS_DUPLICATE")
    if any(rule.observable_ref != observable_ref for rule in rules):
        raise V31ExperimentContractError("MONITOR_RULE_OBSERVABLE_MISMATCH")
    return tuple(sorted(rules, key=lambda rule: rule.role.value))


def build_typed_path_monitor_plan(
    *,
    experiment_contract: Mapping[str, Any],
    monitor_plan_id: str,
    cycle_id: str,
    cycle_index: int,
    origin_bindings: Mapping[str, Mapping[str, str]],
    decision_at: str,
    observable_ref: str,
    source_request_id: str,
    rules: Sequence[FrozenMonitorRule],
) -> dict[str, Any]:
    """Freeze a pre-outcome typed plan for one accepted cycle."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 8
    ):
        raise V31ExperimentContractError("MONITOR_CYCLE_INDEX_INVALID")
    decision = _time(decision_at, "MONITOR_DECISION_AT_INVALID")
    not_before = decision + OUTCOME_HORIZON
    expires = not_before + OUTCOME_GRACE
    observable = _text(observable_ref, "MONITOR_OBSERVABLE_REF_INVALID")
    frozen_rules = _rules(rules, observable)
    document = {
        "schema_id": MONITOR_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "monitor_plan_id": _text(monitor_plan_id, "MONITOR_PLAN_ID_INVALID"),
        "experiment_contract_digest": contract_digest,
        "run_id": experiment_contract["run_id"],
        "cycle_id": _text(cycle_id, "MONITOR_CYCLE_ID_INVALID"),
        "cycle_index": cycle_index,
        "origin_bindings": _origin_bindings(origin_bindings),
        "decision_at": _time_text(decision),
        "outcome_horizon": "1H",
        "outcome_not_before": _time_text(not_before),
        "expires_at": _time_text(expires),
        "observable": {
            "observable_ref": observable,
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "timeframe": "1H",
            "window": "FIRST_PUBLIC_MARK_OBSERVATION_AT_OR_AFTER_1H_HORIZON",
            "horizon_semantics": "ELAPSED_1H_POINT_IN_TIME_NOT_CANDLE_BOUNDARY",
            "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
            "request_method": "GET",
            "source_endpoint": "https://www.okx.com/api/v5/public/mark-price",
            "source_parameters": {
                "instType": "SWAP",
                "instId": "BTC-USDT-SWAP",
            },
            "source_request_id": _text(
                source_request_id, "MONITOR_SOURCE_REQUEST_ID_INVALID"
            ),
        },
        "rules": [rule.to_document() for rule in frozen_rules],
        "quality_gate": {
            "minimum_quality": "MEDIUM",
            "minimum_coverage": "1",
            "allowed_conflict_states": ["NONE"],
        },
        "resolution_policy": {
            "falsifier_precedence": True,
            "confirmation_true_contradiction_false": "FULFILLED_SUPPORTED",
            "contradiction_or_falsifier_true": "FALSIFIED",
            "all_observed_rules_false": "PARTIAL_OTHER",
            "conflicting_or_unusable_evidence": "UNKNOWN_UNRESOLVED",
            "missing_at_expiry": "EXPIRED_UNRESOLVED",
            "UNKNOWN": "NEVER_FALSE_ZERO_OR_IMPUTED",
            "OTHER": "LEGITIMATE_RESIDUAL_OUTCOME",
        },
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "monitor_plan_digest")


def _rule_from_document(value: Mapping[str, Any]) -> FrozenMonitorRule:
    try:
        return FrozenMonitorRule(
            rule_id=value["rule_id"],
            role=MonitorRuleRole(value["role"]),
            observable_ref=value["observable_ref"],
            operator=MonitorOperator(value["operator"]),
            expected=value["expected"],
            unit=value["unit"],
            timeframe=value["timeframe"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentContractError):
            raise
        raise V31ExperimentContractError("MONITOR_RULE_DOCUMENT_INVALID") from exc


def verify_typed_path_monitor_plan(
    plan: Mapping[str, Any],
    *,
    experiment_contract: Mapping[str, Any],
    expected_origin_bindings: Mapping[str, Mapping[str, str]],
) -> str:
    """Verify the plan and its exact origin-object bindings."""

    if not isinstance(plan, Mapping):
        raise V31ExperimentContractError("MONITOR_PLAN_INVALID")
    expected_origins = _origin_bindings(expected_origin_bindings)
    if plan.get("origin_bindings") != expected_origins:
        raise V31ExperimentContractError("MONITOR_ORIGIN_BINDINGS_MISMATCH")
    try:
        supplied = verify_self_digest(plan, "monitor_plan_digest")
        rebuilt = build_typed_path_monitor_plan(
            experiment_contract=experiment_contract,
            monitor_plan_id=plan["monitor_plan_id"],
            cycle_id=plan["cycle_id"],
            cycle_index=plan["cycle_index"],
            origin_bindings=expected_origins,
            decision_at=plan["decision_at"],
            observable_ref=plan["observable"]["observable_ref"],
            source_request_id=plan["observable"]["source_request_id"],
            rules=tuple(_rule_from_document(rule) for rule in plan["rules"]),
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentContractError):
            raise
        raise V31ExperimentContractError("MONITOR_PLAN_INVALID") from exc
    if rebuilt != dict(plan) or supplied != rebuilt["monitor_plan_digest"]:
        raise V31ExperimentContractError("MONITOR_PLAN_RECONSTRUCTION_MISMATCH")
    return supplied


def _compare(actual: Any, operator: MonitorOperator, expected: Any) -> bool:
    if operator is MonitorOperator.EXISTS:
        return actual is not None
    if operator is MonitorOperator.IN:
        return actual in expected
    if operator in {
        MonitorOperator.GT,
        MonitorOperator.GTE,
        MonitorOperator.LT,
        MonitorOperator.LTE,
    }:
        left = _decimal(actual, "OUTCOME_RULE_NUMERIC_COMPARISON_INVALID")
        right = _decimal(expected, "OUTCOME_RULE_NUMERIC_COMPARISON_INVALID")
        if operator is MonitorOperator.GT:
            return left > right
        if operator is MonitorOperator.GTE:
            return left >= right
        if operator is MonitorOperator.LT:
            return left < right
        return left <= right
    if operator is MonitorOperator.EQ:
        return actual == expected
    if operator is MonitorOperator.NE:
        return actual != expected
    raise V31ExperimentContractError("OUTCOME_RULE_OPERATOR_INVALID")


def _observation_from_document(value: Mapping[str, Any]) -> OutcomeObservation:
    try:
        supplied = verify_self_digest(value, "observation_digest")
        observation = OutcomeObservation(
            observable_ref=value["observable_ref"],
            value=value["value"],
            as_of=value["as_of"],
            available_at=value["available_at"],
            missingness=ObservationMissingness(value["missingness"]),
            quality=ObservationQuality(value["quality"]),
            coverage=value["coverage"],
            conflict_state=value["conflict_state"],
            source_request_id=value["source_request_id"],
            source_record_digest=value["source_record_digest"],
            raw_capture_digest=value["raw_capture_digest"],
            datum_digest=value["datum_digest"],
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentContractError):
            raise
        raise V31ExperimentContractError("OUTCOME_OBSERVATION_DOCUMENT_INVALID") from exc
    if observation.to_document() != dict(value) or supplied != value["observation_digest"]:
        raise V31ExperimentContractError("OUTCOME_OBSERVATION_RECONSTRUCTION_MISMATCH")
    return observation


def _prior_receipt_digest(
    prior_receipt: Mapping[str, Any] | None,
    *,
    expected_prior_digest: str | None,
    experiment_contract_digest: str,
    cycle_index: int,
    evaluated_at: datetime,
) -> str | None:
    if cycle_index == 1:
        if prior_receipt is not None or expected_prior_digest is not None:
            raise V31ExperimentContractError("OUTCOME_FIRST_RECEIPT_PREDECESSOR_FORBIDDEN")
        return None
    if not isinstance(prior_receipt, Mapping):
        raise V31ExperimentContractError("OUTCOME_PREVIOUS_RECEIPT_REQUIRED")
    expected = _digest(
        expected_prior_digest,
        "OUTCOME_PREVIOUS_ACCEPTED_HEAD_DIGEST_REQUIRED",
    )
    try:
        digest = verify_self_digest(prior_receipt, "outcome_receipt_digest")
    except (CanonicalContractError, TypeError, ValueError) as exc:
        raise V31ExperimentContractError("OUTCOME_PREVIOUS_RECEIPT_TAMPERED") from exc
    if digest != expected:
        raise V31ExperimentContractError("OUTCOME_PREVIOUS_ACCEPTED_HEAD_MISMATCH")
    if (
        prior_receipt.get("schema_id") != OUTCOME_SCHEMA_ID
        or prior_receipt.get("schema_version") != SCHEMA_VERSION
        or prior_receipt.get("experiment_contract_digest") != experiment_contract_digest
        or prior_receipt.get("cycle_index") != cycle_index - 1
    ):
        raise V31ExperimentContractError("OUTCOME_PREVIOUS_RECEIPT_CHAIN_MISMATCH")
    if _time(prior_receipt.get("evaluated_at"), "OUTCOME_PREVIOUS_TIME_INVALID") >= evaluated_at:
        raise V31ExperimentContractError("OUTCOME_PREVIOUS_RECEIPT_TIME_INVALID")
    return digest


def _resolution(
    *, plan: Mapping[str, Any], observation: OutcomeObservation, evaluated_at: datetime
) -> tuple[list[dict[str, str]], ExpectationOutcome, PathOutcome, str, bool]:
    expires = _time(plan["expires_at"], "OUTCOME_EXPIRY_INVALID")
    usable = (
        observation.missingness is ObservationMissingness.OBSERVED
        and _QUALITY_RANK[observation.quality] >= _QUALITY_RANK[ObservationQuality.MEDIUM]
        and observation.coverage == Decimal("1")
        and observation.conflict_state == "NONE"
    )
    if not usable:
        status = (
            ExpectationOutcome.EXPIRED
            if evaluated_at >= expires
            else ExpectationOutcome.UNKNOWN
        )
        reason = (
            "MISSING_AT_EXPIRY"
            if status is ExpectationOutcome.EXPIRED
            else "MISSING_OR_QUALITY_GATE_FAILED"
        )
        results = [
            {"rule_id": rule["rule_id"], "role": rule["role"], "truth": "UNKNOWN"}
            for rule in plan["rules"]
        ]
        return results, status, PathOutcome.UNRESOLVED, reason, True

    truths: dict[MonitorRuleRole, RuleTruth] = {}
    results = []
    for rule_document in plan["rules"]:
        rule = _rule_from_document(rule_document)
        truth = (
            RuleTruth.TRUE
            if _compare(observation.value, rule.operator, rule.expected)
            else RuleTruth.FALSE
        )
        truths[rule.role] = truth
        results.append(
            {"rule_id": rule.rule_id, "role": rule.role.value, "truth": truth.value}
        )
    if truths[MonitorRuleRole.FALSIFIER] is RuleTruth.TRUE or truths[
        MonitorRuleRole.CONTRADICTION
    ] is RuleTruth.TRUE:
        return (
            results,
            ExpectationOutcome.FALSIFIED,
            PathOutcome.FALSIFIED,
            "CONTRADICTION_OR_FALSIFIER_TRUE",
            False,
        )
    if truths[MonitorRuleRole.CONFIRMATION] is RuleTruth.TRUE:
        return (
            results,
            ExpectationOutcome.FULFILLED,
            PathOutcome.SUPPORTED,
            "CONFIRMATION_TRUE",
            False,
        )
    return (
        results,
        ExpectationOutcome.PARTIAL,
        PathOutcome.OTHER,
        "ALL_OBSERVED_RULES_FALSE",
        False,
    )


def build_path_outcome_receipt(
    *,
    experiment_contract: Mapping[str, Any],
    monitor_plan: Mapping[str, Any],
    expected_origin_bindings: Mapping[str, Mapping[str, str]],
    outcome_receipt_id: str,
    evaluated_at: str,
    evaluator_version: str,
    observation: OutcomeObservation,
    previous_outcome_receipt: Mapping[str, Any] | None = None,
    expected_previous_outcome_receipt_digest: str | None = None,
) -> dict[str, Any]:
    """Resolve one due plan without reading early, imputing, or breaking lineage."""

    contract_digest = verify_minimal_experiment_contract(experiment_contract)
    plan_digest = verify_typed_path_monitor_plan(
        monitor_plan,
        experiment_contract=experiment_contract,
        expected_origin_bindings=expected_origin_bindings,
    )
    if not isinstance(observation, OutcomeObservation):
        raise V31ExperimentContractError("OUTCOME_OBSERVATION_REQUIRED")
    evaluated = _time(evaluated_at, "OUTCOME_EVALUATED_AT_INVALID")
    not_before = _time(monitor_plan["outcome_not_before"], "OUTCOME_NOT_BEFORE_INVALID")
    expires = _time(monitor_plan["expires_at"], "OUTCOME_EXPIRY_INVALID")
    if evaluated < not_before:
        raise V31ExperimentContractError("OUTCOME_READ_BEFORE_NOT_BEFORE_FORBIDDEN")
    if evaluated > expires:
        raise V31ExperimentContractError("OUTCOME_EVALUATION_AFTER_EXPIRY_FORBIDDEN")
    observed_as_of = _time(observation.as_of, "OUTCOME_OBSERVATION_TIME_INVALID")
    available_at = _time(observation.available_at, "OUTCOME_OBSERVATION_TIME_INVALID")
    if observed_as_of < not_before or observed_as_of > evaluated:
        raise V31ExperimentContractError("OUTCOME_WRONG_1H_WINDOW")
    if available_at > evaluated:
        raise V31ExperimentContractError("OUTCOME_FUTURE_DATA_FORBIDDEN")
    if observation.observable_ref != monitor_plan["observable"]["observable_ref"]:
        raise V31ExperimentContractError("OUTCOME_OBSERVABLE_MISMATCH")
    if observation.source_request_id != monitor_plan["observable"]["source_request_id"]:
        raise V31ExperimentContractError("OUTCOME_SOURCE_REQUEST_MISMATCH")
    previous_digest = _prior_receipt_digest(
        previous_outcome_receipt,
        expected_prior_digest=expected_previous_outcome_receipt_digest,
        experiment_contract_digest=contract_digest,
        cycle_index=monitor_plan["cycle_index"],
        evaluated_at=evaluated,
    )
    rule_results, expectation, path, attribution, coverage_loss = _resolution(
        plan=monitor_plan,
        observation=observation,
        evaluated_at=evaluated,
    )
    document = {
        "schema_id": OUTCOME_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "outcome_receipt_id": _text(
            outcome_receipt_id, "OUTCOME_RECEIPT_ID_INVALID"
        ),
        "experiment_contract_digest": contract_digest,
        "monitor_plan_digest": plan_digest,
        "run_id": monitor_plan["run_id"],
        "cycle_id": monitor_plan["cycle_id"],
        "cycle_index": monitor_plan["cycle_index"],
        "origin_bindings": _origin_bindings(expected_origin_bindings),
        "evaluated_at": _time_text(evaluated),
        "evaluator_version": _text(
            evaluator_version, "OUTCOME_EVALUATOR_VERSION_INVALID"
        ),
        "previous_outcome_receipt_digest": previous_digest,
        "observation": observation.to_document(),
        "rule_results": rule_results,
        "expectation_outcome": expectation.value,
        "path_outcome": path.value,
        "failure_attribution": attribution,
        "coverage_loss": coverage_loss,
        "unknown_counted_as_coverage_loss": coverage_loss,
        "authority_boundary": _authority_boundary(),
    }
    return self_digest(document, "outcome_receipt_digest")


def verify_path_outcome_receipt(
    receipt: Mapping[str, Any],
    *,
    experiment_contract: Mapping[str, Any],
    monitor_plan: Mapping[str, Any],
    expected_origin_bindings: Mapping[str, Mapping[str, str]],
    previous_outcome_receipt: Mapping[str, Any] | None = None,
    expected_previous_outcome_receipt_digest: str | None = None,
) -> str:
    """Reconstruct a receipt, including its origin and previous-receipt links."""

    if not isinstance(receipt, Mapping):
        raise V31ExperimentContractError("OUTCOME_RECEIPT_INVALID")
    try:
        supplied = verify_self_digest(receipt, "outcome_receipt_digest")
        observation = _observation_from_document(receipt["observation"])
        rebuilt = build_path_outcome_receipt(
            experiment_contract=experiment_contract,
            monitor_plan=monitor_plan,
            expected_origin_bindings=expected_origin_bindings,
            outcome_receipt_id=receipt["outcome_receipt_id"],
            evaluated_at=receipt["evaluated_at"],
            evaluator_version=receipt["evaluator_version"],
            observation=observation,
            previous_outcome_receipt=previous_outcome_receipt,
            expected_previous_outcome_receipt_digest=(
                expected_previous_outcome_receipt_digest
            ),
        )
    except (CanonicalContractError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31ExperimentContractError):
            raise
        raise V31ExperimentContractError("OUTCOME_RECEIPT_INVALID") from exc
    if rebuilt != dict(receipt) or supplied != rebuilt["outcome_receipt_digest"]:
        raise V31ExperimentContractError("OUTCOME_RECEIPT_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "APPROVED_THEORY_SHA256",
    "ClosedHourCycleBinding",
    "EXPERIMENT_SCHEMA_ID",
    "ExpectationOutcome",
    "FrozenMonitorRule",
    "MonitorOperator",
    "MonitorRuleRole",
    "MONITOR_SCHEMA_ID",
    "ObservationMissingness",
    "ObservationQuality",
    "OutcomeObservation",
    "OUTCOME_SCHEMA_ID",
    "PathOutcome",
    "RuleTruth",
    "V31ExperimentContractError",
    "build_minimal_experiment_contract",
    "build_path_outcome_receipt",
    "build_typed_path_monitor_plan",
    "verify_minimal_experiment_contract",
    "verify_eight_closed_hour_cycles",
    "verify_frozen_association_receipt",
    "verify_path_outcome_receipt",
    "verify_typed_path_monitor_plan",
]
