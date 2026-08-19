"""Evidence-bound evaluation limits for the V3.1 successor experiment.

The active public BTC experiment has eight ordinal, non-executable research
cycles.  Eight local cycles can test contract fidelity and future-outcome
capture, but they cannot establish predictive increment, calibration,
cost-after-return, or cross-regime generalization.  This pure Domain contract
freezes that boundary and the minimum design of a later, separately authorized
evaluation.  It intentionally contains no performance calculator, forecast
probability, EV, order, account, or portfolio mutation path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts.canonical import self_digest, verify_self_digest
from .v31_association_preregistration_v2 import (
    CURRENT_EXPERIMENT_CYCLE_CAP,
    INSTRUMENT_ID,
    verify_v31_association_preregistration_v2,
)


class V31EvaluationContractError(ValueError):
    """A successor evaluation contract or status failed closed."""


SCHEMA_ID = "theory_paper_v2_v31_evaluation_contract_v2"
STATUS_SCHEMA_ID = "theory_paper_v2_v31_evaluation_status_v2"
SCHEMA_VERSION = "2.0.0"

PREDICTIVE_INCREMENT_MIN_OUTCOMES = 240
CALIBRATION_PROMOTION_MIN_FORECASTS = 500
COST_AFTER_RETURN_MIN_COMPLETED_EPISODES = 100
CROSS_REGIME_MIN_TOTAL_OUTCOMES = 480
CROSS_REGIME_MIN_REGIMES = 3
CROSS_REGIME_MIN_OUTCOMES_PER_REGIME = 96


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31EvaluationContractError(code)
    return value.strip()


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31EvaluationContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31EvaluationContractError(code) from exc
    if parsed.tzinfo is None:
        raise V31EvaluationContractError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _count(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise V31EvaluationContractError(code)
    return value


def build_v31_evaluation_contract_v2(
    *,
    association_preregistration: Mapping[str, Any],
    run_scope_id: str,
    frozen_at: str,
) -> dict[str, Any]:
    """Freeze evidence gates without pretending the current run can meet them."""

    association_digest = verify_v31_association_preregistration_v2(
        association_preregistration
    )
    scope = _text(run_scope_id, "EVALUATION_RUN_SCOPE_INVALID")
    if scope != association_preregistration["run_scope_id"]:
        raise V31EvaluationContractError(
            "EVALUATION_ASSOCIATION_RUN_SCOPE_MISMATCH"
        )
    frozen = _time(frozen_at, "EVALUATION_FROZEN_AT_INVALID")
    association_frozen = _time(
        association_preregistration["frozen_at"],
        "EVALUATION_ASSOCIATION_FROZEN_AT_INVALID",
    )
    if frozen < association_frozen:
        raise V31EvaluationContractError(
            "EVALUATION_PRECEDES_ASSOCIATION_PREREGISTRATION"
        )

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": scope,
        "frozen_at": _time_text(frozen),
        "instrument_id": INSTRUMENT_ID,
        "association_preregistration_digest": association_digest,
        "current_experiment_scope": {
            "maximum_accepted_cycles": CURRENT_EXPERIMENT_CYCLE_CAP,
            "maximum_resolved_outcomes": CURRENT_EXPERIMENT_CYCLE_CAP,
            "timeframe": "1H",
            "probability_mode": "ORDINAL_VECTOR_NOT_PROBABILITY",
            "public_data_only": True,
            "portfolio_mode": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
            "initial_and_persistent_portfolio_state": "FLAT",
            "portfolio_mutation": False,
            "reentry_state_machine": False,
            "selection_is_non_executable_research_label": True,
        },
        "predictive_increment": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_run_eligible": False,
            "minimum_resolved_prospective_outcomes": (
                PREDICTIVE_INCREMENT_MIN_OUTCOMES
            ),
            "minimum_count_alone_is_sufficient": False,
            "pre_run_power_analysis_required": True,
            "minimum_chronological_evaluation_blocks": 3,
            "minimum_outcomes_per_block": 80,
            "comparators": [
                "FROZEN_NO_INFORMATION_LAYER_ABLATION",
                "FROZEN_DETERMINISTIC_SHADOW",
                "FROZEN_PRIOR_LEAD_PERSISTENCE_BASELINE",
            ],
            "same_sample_requirement": (
                "IDENTICAL_PIT_OUTCOMES_COVERAGE_AND_HORIZON"
            ),
            "primary_estimand": (
                "PAIRED_PATH_DISCRIMINATION_RATE_INCREMENT"
            ),
            "interval_method": (
                "PRE_REGISTERED_SERIAL_DEPENDENCE_AWARE_PAIRED_INTERVAL_95"
            ),
            "success_rule": (
                "PRIMARY_INCREMENT_INTERVAL_LOWER_ABOVE_ZERO_AND_"
                "UNKNOWN_COVERAGE_NOT_WORSE"
            ),
            "unknown_policy": (
                "UNRESOLVED_OUTCOMES_EXCLUDED_FROM_HIT_DENOMINATOR_"
                "AND_REPORTED_AS_COVERAGE_LOSS"
            ),
            "forbidden_substitutes": [
                "LOCAL_TEST_PASS",
                "ACCEPTED_STATE_COUNT",
                "API_REACHABILITY",
                "IN_SAMPLE_ASSOCIATION",
            ],
        },
        "probability_calibration": {
            "current_status": "NOT_APPLICABLE_ORDINAL_ONLY",
            "current_probability_mode": "ORDINAL_VECTOR_NOT_PROBABILITY",
            "brier_log_ece_allowed_now": False,
            "promotion_requires_new_version_and_authority": True,
            "future_minimum_prospective_forecasts": (
                CALIBRATION_PROMOTION_MIN_FORECASTS
            ),
            "minimum_count_alone_is_sufficient": False,
            "pre_run_precision_analysis_required": True,
            "future_event_contract": (
                "MUTUALLY_EXCLUSIVE_EXHAUSTIVE_FIXED_HORIZON_PARTITION"
            ),
            "future_requirements": [
                "INDEPENDENT_CALIBRATION_WINDOW",
                "PRE_REGISTERED_PROPER_SCORE",
                "PRE_REGISTERED_CALIBRATION_BINS",
                "SHARPNESS_AND_COVERAGE_REPORTED_SEPARATELY",
                "MODEL_AND_EVENT_CONTRACT_DIGESTS_BOUND_TO_EACH_FORECAST",
            ],
            "ordinal_values_are_probabilities": False,
        },
        "cost_after_return": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_claim_scope": "EXCLUDED_NO_CLAIM",
            "current_run_eligible": False,
            "future_minimum_completed_episodes": (
                COST_AFTER_RETURN_MIN_COMPLETED_EPISODES
            ),
            "minimum_count_alone_is_sufficient": False,
            "pre_run_power_analysis_required": True,
            "future_requires_separate_authority": True,
            "future_cost_ledger_requirements": [
                "POINT_IN_TIME_FEES",
                "POINT_IN_TIME_FUNDING",
                "BID_ASK_AND_SLIPPAGE_MODEL",
                "MARK_TO_MARKET_AND_TERMINAL_CLOSE_RULE",
                "SAME_COSTS_FOR_CANDIDATE_AND_BASELINES",
            ],
            "future_outputs_kept_separate": [
                "GROSS_RETURN",
                "FEES",
                "FUNDING",
                "SLIPPAGE",
                "NET_RETURN",
                "MAX_DRAWDOWN",
                "TAIL_LOSS",
                "REENTRY_DELAY",
                "PATH_CAPTURE",
            ],
            "static_flat_shadow_is_performance_evidence": False,
        },
        "cross_regime_generalization": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_run_eligible": False,
            "future_minimum_total_outcomes": CROSS_REGIME_MIN_TOTAL_OUTCOMES,
            "future_minimum_pre_registered_regimes": CROSS_REGIME_MIN_REGIMES,
            "future_minimum_outcomes_per_regime": (
                CROSS_REGIME_MIN_OUTCOMES_PER_REGIME
            ),
            "minimum_counts_alone_are_sufficient": False,
            "pre_run_power_analysis_by_regime_required": True,
            "future_minimum_chronological_blocks_per_regime": 2,
            "regime_classifier_must_precede_outcomes": True,
            "regime_classifier_digest_required": True,
            "pooled_only_result_forbidden": True,
            "success_rule": (
                "PRIMARY_INCREMENT_DIRECTION_PRESERVED_WITH_"
                "PRE_REGISTERED_INTERVAL_IN_EACH_CLAIMED_REGIME"
            ),
        },
        "association_evaluation": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "smallest_candidate_minimum_sample": 135,
            "current_cycle_cap": CURRENT_EXPERIMENT_CYCLE_CAP,
            "multiplicity": (
                "BENJAMINI_YEKUTIELI_FDR_PLUS_HOLM_CONFIRMATORY_FWER"
            ),
            "ordinary_bh_enabled": False,
            "reason": "CURRENT_EIGHT_CYCLES_BELOW_MINIMUM_SAMPLE",
        },
        "portfolio_and_reentry_boundary": {
            "portfolio": "EXCLUDED_NO_CLAIM",
            "reentry": "EXCLUDED_NO_CLAIM",
            "static_flat_shadow": "ALLOWED_CONTEXT_ONLY",
            "portfolio_writeback": False,
            "portfolio_performance_claim": False,
            "reentry_performance_claim": False,
        },
        "global_claim_boundary": {
            "local_pass_is_predictive_validity": False,
            "local_pass_is_profitability": False,
            "contract_fidelity_is_market_validity": False,
            "minimum_evidence_counts_are_sufficiency_proof": False,
            "unknown_may_be_promoted_by_narrative": False,
            "mid_run_threshold_or_metric_change": "FORBIDDEN",
            "future_outcome_read_before_due": "FORBIDDEN",
            "forecast_probability_output_allowed": False,
            "ev_allowed": False,
        },
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "evaluation_contract_digest")


def verify_v31_evaluation_contract_v2(
    document: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping):
        raise V31EvaluationContractError("EVALUATION_CONTRACT_INVALID")
    try:
        supplied = verify_self_digest(document, "evaluation_contract_digest")
        rebuilt = build_v31_evaluation_contract_v2(
            association_preregistration=association_preregistration,
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31EvaluationContractError):
            raise
        raise V31EvaluationContractError("EVALUATION_CONTRACT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt["evaluation_contract_digest"]:
        raise V31EvaluationContractError(
            "EVALUATION_CONTRACT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_current_scope_evaluation_status_v2(
    *,
    evaluation_contract: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
    accepted_cycle_count: int,
    resolved_outcome_count: int,
    assessed_at: str,
) -> dict[str, Any]:
    """Report current evidence without any count-only promotion path."""

    contract_digest = verify_v31_evaluation_contract_v2(
        evaluation_contract, association_preregistration
    )
    accepted = _count(accepted_cycle_count, "EVALUATION_ACCEPTED_COUNT_INVALID")
    resolved = _count(resolved_outcome_count, "EVALUATION_OUTCOME_COUNT_INVALID")
    if (
        accepted > CURRENT_EXPERIMENT_CYCLE_CAP
        or resolved > accepted
        or resolved > CURRENT_EXPERIMENT_CYCLE_CAP
    ):
        raise V31EvaluationContractError(
            "EVALUATION_CURRENT_SCOPE_COUNT_OUT_OF_RANGE"
        )
    status = {
        "schema_id": STATUS_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": evaluation_contract["run_scope_id"],
        "instrument_id": INSTRUMENT_ID,
        "evaluation_contract_digest": contract_digest,
        "association_preregistration_digest": evaluation_contract[
            "association_preregistration_digest"
        ],
        "assessed_at": _time_text(_time(assessed_at, "EVALUATION_STATUS_TIME_INVALID")),
        "accepted_cycle_count": accepted,
        "resolved_outcome_count": resolved,
        "current_scope_complete": (
            accepted == CURRENT_EXPERIMENT_CYCLE_CAP
            and resolved == CURRENT_EXPERIMENT_CYCLE_CAP
        ),
        "evidence_states": [
            {
                "question": "PREDICTIVE_INCREMENT",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": (
                    "CURRENT_SCOPE_BELOW_240_RESOLVED_PROSPECTIVE_OUTCOMES"
                ),
            },
            {
                "question": "PROBABILITY_CALIBRATION",
                "status": "NOT_APPLICABLE_ORDINAL_ONLY",
                "claim_scope": "NO_BRIER_LOG_ECE_CLAIM",
                "reason": "ORDINAL_VECTOR_IS_NOT_A_FORECAST_DISTRIBUTION",
            },
            {
                "question": "COST_AFTER_RETURN",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "EXCLUDED_NO_CLAIM",
                "reason": "STATIC_FLAT_SHADOW_NO_PORTFOLIO_MUTATION",
            },
            {
                "question": "CROSS_REGIME_GENERALIZATION",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": "CURRENT_SCOPE_HAS_NO_QUALIFYING_REGIME_DESIGN",
            },
            {
                "question": "ASSOCIATION_FAMILY_DISCOVERY",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": "EIGHT_CYCLES_BELOW_SMALLEST_MINIMUM_SAMPLE_135",
            },
        ],
        "portfolio_scope": "STATIC_COUNTERFACTUAL_FLAT_SHADOW",
        "portfolio_mutation": False,
        "reentry_scope": "EXCLUDED_NO_CLAIM",
        "static_flat_shadow_only": True,
        "forecast_probability_output": None,
        "ev_output": None,
        "local_contract_pass_may_promote_market_claim": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(status, "evaluation_status_digest")


def verify_current_scope_evaluation_status_v2(
    status: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
) -> str:
    if not isinstance(status, Mapping):
        raise V31EvaluationContractError("EVALUATION_STATUS_INVALID")
    try:
        supplied = verify_self_digest(status, "evaluation_status_digest")
        rebuilt = build_current_scope_evaluation_status_v2(
            evaluation_contract=evaluation_contract,
            association_preregistration=association_preregistration,
            accepted_cycle_count=status["accepted_cycle_count"],
            resolved_outcome_count=status["resolved_outcome_count"],
            assessed_at=status["assessed_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31EvaluationContractError):
            raise
        raise V31EvaluationContractError("EVALUATION_STATUS_INVALID") from exc
    if dict(status) != rebuilt or supplied != rebuilt["evaluation_status_digest"]:
        raise V31EvaluationContractError(
            "EVALUATION_STATUS_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "CALIBRATION_PROMOTION_MIN_FORECASTS",
    "COST_AFTER_RETURN_MIN_COMPLETED_EPISODES",
    "CROSS_REGIME_MIN_OUTCOMES_PER_REGIME",
    "CROSS_REGIME_MIN_REGIMES",
    "CROSS_REGIME_MIN_TOTAL_OUTCOMES",
    "PREDICTIVE_INCREMENT_MIN_OUTCOMES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "STATUS_SCHEMA_ID",
    "V31EvaluationContractError",
    "build_current_scope_evaluation_status_v2",
    "build_v31_evaluation_contract_v2",
    "verify_current_scope_evaluation_status_v2",
    "verify_v31_evaluation_contract_v2",
]
