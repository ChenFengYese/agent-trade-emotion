"""Evidence and claim boundaries for the V3.2 15-minute process pilot.

Sixteen prospective decisions and forty-eight scheduled horizon observations can
qualify process durability and support short-window description.  They cannot
establish predictive increment, probability calibration, cost-after-return, or
cross-regime generalization.  This pure Domain module freezes the later evidence
gates and keeps every unsupported market claim ``UNKNOWN_NOT_EVALUATED``.

No builder in this module calculates a score, probability, EV, fill, return, or
portfolio state.  Threshold counts are necessary gates, never sufficient proof.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .contracts.canonical import self_digest, verify_self_digest
from .v32_association_preregistration import (
    INSTRUMENT_ID,
    PILOT_ANALYSIS_CYCLE_CAP,
    PILOT_ID,
    verify_v32_association_preregistration,
)


class V32EvaluationContractError(ValueError):
    """The V3.2 evaluation contract or status failed closed."""


SCHEMA_ID = "theory_paper_v2_v32_evaluation_contract_v1"
STATUS_SCHEMA_ID = "theory_paper_v2_v32_evaluation_status_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "evaluation_contract_digest"
STATUS_DIGEST_FIELD = "evaluation_status_digest"

PILOT_OUTCOME_SCHEDULE_COUNT = 48
PREDICTIVE_INCREMENT_MIN_DECISIONS = 240
CALIBRATION_MIN_PROSPECTIVE_FORECASTS = 500
COST_AFTER_RETURN_MIN_COMPLETED_EPISODES = 100
CROSS_REGIME_MIN_TOTAL_DECISIONS = 480
CROSS_REGIME_MIN_REGIMES = 3
CROSS_REGIME_MIN_DECISIONS_PER_REGIME = 96


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V32EvaluationContractError(code)
    return value.strip()


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32EvaluationContractError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32EvaluationContractError(code) from exc
    if parsed.tzinfo is None:
        raise V32EvaluationContractError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _count(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise V32EvaluationContractError(code)
    return value


def build_v32_evaluation_contract(
    *,
    association_preregistration: Mapping[str, Any],
    run_scope_id: str,
    frozen_at: str,
) -> dict[str, Any]:
    """Freeze process-pilot limits and separately authorized future gates."""

    association_digest = verify_v32_association_preregistration(
        association_preregistration
    )
    scope = _text(run_scope_id, "V32_EVALUATION_RUN_SCOPE_INVALID")
    if scope != association_preregistration["run_scope_id"]:
        raise V32EvaluationContractError(
            "V32_EVALUATION_ASSOCIATION_RUN_SCOPE_MISMATCH"
        )
    frozen = _timestamp(frozen_at, "V32_EVALUATION_FROZEN_AT_INVALID")
    association_frozen = _timestamp(
        association_preregistration["frozen_at"],
        "V32_EVALUATION_ASSOCIATION_FROZEN_AT_INVALID",
    )
    if frozen < association_frozen:
        raise V32EvaluationContractError(
            "V32_EVALUATION_PRECEDES_ASSOCIATION_PREREGISTRATION"
        )

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": scope,
        "frozen_at": _time_text(frozen),
        "instrument_id": INSTRUMENT_ID,
        "pilot_id": PILOT_ID,
        "association_preregistration_digest": association_digest,
        "current_pilot_scope": {
            "analysis_cycle_count": PILOT_ANALYSIS_CYCLE_CAP,
            "analysis_timeframe": "15M",
            "outcome_horizons": ["15M", "1H", "4H"],
            "scheduled_outcome_count": PILOT_OUTCOME_SCHEDULE_COUNT,
            "scope_class": "PROCESS_AND_SHORT_WINDOW_DESCRIPTIVE_ONLY",
            "public_data_only": True,
            "probability_mode": "ORDINAL_PLAUSIBILITY_NOT_PROBABILITY",
            "fill_observation": False,
            "cost_ledger": False,
            "portfolio_mutation": False,
            "selection_is_non_executable_research_label": True,
            "three_horizons_do_not_create_three_independent_decisions": True,
        },
        "process_evaluation": {
            "eligible_in_current_pilot": True,
            "questions": [
                "DURABLE_PROPOSAL_COMPILE_SELECTION_COMMIT",
                "FULL_CONTEXT_THEN_15M_DELTA_CONTINUITY",
                "HYPOTHESIS_OPPOSITION_EXPIRY_AND_REVISION_REPLAY",
                "OUTCOME_RAW_FIRST_SHARED_TICK_AND_NO_FUTURE_LEAKAGE",
            ],
            "reportable_outputs": [
                "CONTRACT_FIDELITY",
                "COVERAGE_AND_UNKNOWN_COUNTS",
                "ORDINAL_PATH_LABELS",
                "MFE_MAE_AND_TRIGGER_TIMING_DESCRIPTION",
                "PROCESS_FAILURES",
            ],
            "forbidden_promotions": [
                "PREDICTIVE_VALIDITY",
                "CALIBRATION",
                "PROFITABILITY",
                "CROSS_REGIME_GENERALIZATION",
                "PRODUCTION_READINESS",
            ],
        },
        "predictive_increment": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_pilot_eligible": False,
            "minimum_resolved_prospective_decisions": (
                PREDICTIVE_INCREMENT_MIN_DECISIONS
            ),
            "minimum_count_alone_is_sufficient": False,
            "pre_run_power_analysis_required": True,
            "minimum_chronological_blocks": 3,
            "minimum_decisions_per_block": 80,
            "same_sample_requirement": (
                "IDENTICAL_PIT_INPUT_OUTCOME_HORIZON_COVERAGE_AND_OPPORTUNITY_SET"
            ),
            "comparators": [
                "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
                "WAIT_ONLY",
                "SIMPLE_15M_TREND",
                "NO_RSI_REFERENCE",
                "ALWAYS_LONG_PUBLIC_MARK_REFERENCE",
            ],
            "baseline_output_requirement": (
                "FROZEN_POLICY_ID_VERSION_DIGEST_AND_REPLAYABLE_INPUT_OUTPUT_"
                "RECEIPT_OR_UNKNOWN_NOT_COMPUTED"
            ),
            "terminal_mark_limit": (
                "DIRECTION_ONLY_MFE_MAE_AND_PATH_REMAIN_UNKNOWN_WITHOUT_"
                "INTRAHORIZON_PUBLIC_PATH"
            ),
            "primary_estimand": "PAIRED_PROSPECTIVE_PATH_DISCRIMINATION_INCREMENT",
            "serial_dependence_aware_interval_required": True,
            "unknown_reported_as_coverage_loss_not_hit_or_miss": True,
            "local_pass_or_outcome_count_is_efficacy": False,
        },
        "probability_calibration": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_pilot_eligible": False,
            "current_probability_mode": "ORDINAL_PLAUSIBILITY_NOT_PROBABILITY",
            "brier_log_ece_allowed_in_current_pilot": False,
            "minimum_prospective_probability_forecasts": (
                CALIBRATION_MIN_PROSPECTIVE_FORECASTS
            ),
            "minimum_count_alone_is_sufficient": False,
            "promotion_requires_new_version_and_separate_authority": True,
            "future_event_contract": (
                "MUTUALLY_EXCLUSIVE_EXHAUSTIVE_FIXED_HORIZON_PARTITION"
            ),
            "future_requirements": [
                "INDEPENDENT_CALIBRATION_WINDOW",
                "PRE_REGISTERED_PROPER_SCORE",
                "PRE_REGISTERED_CALIBRATION_BINS",
                "SHARPNESS_AND_COVERAGE_REPORTED_SEPARATELY",
                "FORECAST_MODEL_AND_EVENT_CONTRACT_DIGEST_BOUND_PER_FORECAST",
            ],
            "ordinal_weights_are_probabilities": False,
        },
        "cost_after_return": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_pilot_eligible": False,
            "current_claim_scope": "EXCLUDED_NO_LEGAL_FILL_OR_COST_EPISODE_CONTRACT",
            "minimum_completed_prospective_episodes": (
                COST_AFTER_RETURN_MIN_COMPLETED_EPISODES
            ),
            "minimum_count_alone_is_sufficient": False,
            "pre_run_power_analysis_required": True,
            "separate_authority_required": True,
            "independent_contracts_required": [
                "PROSPECTIVE_EPISODE_DEFINITION_AND_TERMINATION_CONTRACT",
                "LEGAL_FILL_MODEL_OR_OBSERVED_FILL_CONTRACT",
                "POINT_IN_TIME_FEE_FUNDING_SPREAD_AND_SLIPPAGE_CONTRACT",
                "SAME_COST_AND_OPPORTUNITY_SET_FOR_CANDIDATE_AND_BASELINES",
            ],
            "touch_is_fill": False,
            "limit_or_stop_touch_is_realized_pnl": False,
            "future_outputs_kept_separate": [
                "GROSS_RETURN",
                "FEES",
                "FUNDING",
                "SPREAD_AND_SLIPPAGE",
                "NET_RETURN",
                "MAX_DRAWDOWN",
                "TAIL_LOSS",
                "TURNOVER",
            ],
        },
        "cross_regime_generalization": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_pilot_eligible": False,
            "minimum_resolved_prospective_decisions": (
                CROSS_REGIME_MIN_TOTAL_DECISIONS
            ),
            "minimum_pre_registered_regimes": CROSS_REGIME_MIN_REGIMES,
            "minimum_decisions_per_regime": (
                CROSS_REGIME_MIN_DECISIONS_PER_REGIME
            ),
            "minimum_counts_alone_are_sufficient": False,
            "pre_run_power_analysis_by_regime_required": True,
            "minimum_chronological_blocks_per_regime": 2,
            "regime_classifier_must_precede_outcomes": True,
            "regime_classifier_digest_required": True,
            "pooled_only_result_forbidden": True,
            "success_rule": (
                "PRE_REGISTERED_INCREMENT_DIRECTION_AND_INTERVAL_CRITERION_"
                "SATISFIED_IN_EACH_CLAIMED_REGIME"
            ),
        },
        "association_evaluation": {
            "current_status": "UNKNOWN_NOT_EVALUATED",
            "current_pilot_eligible": False,
            "candidate_count": 144,
            "smallest_candidate_minimum_observed_sample": 77,
            "current_decision_count": PILOT_ANALYSIS_CYCLE_CAP,
            "multiplicity": (
                "BENJAMINI_YEKUTIELI_FDR_PLUS_HOLM_CONFIRMATORY_FWER"
            ),
            "ordinary_bh_enabled": False,
            "reason": "SIXTEEN_DECISIONS_BELOW_SMALLEST_FROZEN_WINDOW_SAMPLE",
        },
        "global_claim_boundary": {
            "contract_fidelity_is_market_validity": False,
            "short_window_description_is_predictive_increment": False,
            "minimum_evidence_counts_are_sufficiency_proof": False,
            "unknown_may_be_promoted_by_narrative": False,
            "mid_run_candidate_window_horizon_or_metric_change": "FORBIDDEN",
            "future_outcome_read_before_due": "FORBIDDEN",
            "causal_claim_allowed": False,
            "forecast_probability_output_allowed": False,
            "brier_ece_output_allowed": False,
            "ev_allowed": False,
            "profitability_claim_allowed": False,
        },
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_evaluation_contract(
    document: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
) -> str:
    """Reconstruct every field and reject re-digested threshold drift."""

    if not isinstance(document, Mapping):
        raise V32EvaluationContractError("V32_EVALUATION_CONTRACT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = build_v32_evaluation_contract(
            association_preregistration=association_preregistration,
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32EvaluationContractError):
            raise
        raise V32EvaluationContractError(
            "V32_EVALUATION_CONTRACT_INVALID"
        ) from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32EvaluationContractError(
            "V32_EVALUATION_CONTRACT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def build_v32_current_scope_evaluation_status(
    *,
    evaluation_contract: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
    accepted_analysis_cycle_count: int,
    terminal_outcome_schedule_count: int,
    assessed_at: str,
) -> dict[str, Any]:
    """Describe pilot evidence without a count-only market-claim promotion."""

    contract_digest = verify_v32_evaluation_contract(
        evaluation_contract, association_preregistration
    )
    accepted = _count(
        accepted_analysis_cycle_count,
        "V32_EVALUATION_ACCEPTED_CYCLE_COUNT_INVALID",
    )
    terminal = _count(
        terminal_outcome_schedule_count,
        "V32_EVALUATION_TERMINAL_OUTCOME_COUNT_INVALID",
    )
    if (
        accepted > PILOT_ANALYSIS_CYCLE_CAP
        or terminal > PILOT_OUTCOME_SCHEDULE_COUNT
        or terminal > accepted * 3
    ):
        raise V32EvaluationContractError(
            "V32_EVALUATION_CURRENT_SCOPE_COUNT_OUT_OF_RANGE"
        )

    complete = (
        accepted == PILOT_ANALYSIS_CYCLE_CAP
        and terminal == PILOT_OUTCOME_SCHEDULE_COUNT
    )
    assessed = _timestamp(assessed_at, "V32_EVALUATION_STATUS_TIME_INVALID")
    contract_frozen = _timestamp(
        evaluation_contract["frozen_at"],
        "V32_EVALUATION_CONTRACT_FROZEN_AT_INVALID",
    )
    if assessed < contract_frozen:
        raise V32EvaluationContractError(
            "V32_EVALUATION_STATUS_PRECEDES_CONTRACT"
        )
    status = {
        "schema_id": STATUS_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": evaluation_contract["run_scope_id"],
        "instrument_id": INSTRUMENT_ID,
        "pilot_id": PILOT_ID,
        "evaluation_contract_digest": contract_digest,
        "association_preregistration_digest": evaluation_contract[
            "association_preregistration_digest"
        ],
        "assessed_at": _time_text(assessed),
        "accepted_analysis_cycle_count": accepted,
        "terminal_outcome_schedule_count": terminal,
        "current_scope_complete": complete,
        "current_reportable_scope": (
            "PROCESS_AND_SHORT_WINDOW_DESCRIPTIVE_ONLY"
        ),
        "process_completion_fact": (
            "COMPLETE_COUNTS_OBSERVED" if complete else "INCOMPLETE_COUNTS_OBSERVED"
        ),
        "evidence_states": [
            {
                "question": "PREDICTIVE_INCREMENT",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": "CURRENT_SCOPE_BELOW_240_PROSPECTIVE_DECISIONS",
            },
            {
                "question": "PROBABILITY_CALIBRATION",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_BRIER_LOG_ECE_CLAIM",
                "reason": (
                    "ORDINAL_PLAUSIBILITY_IS_NOT_A_PROBABILITY_FORECAST_"
                    "AND_SCOPE_BELOW_500"
                ),
            },
            {
                "question": "COST_AFTER_RETURN",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "EXCLUDED_NO_CLAIM",
                "reason": "NO_INDEPENDENT_LEGAL_FILL_AND_COST_EPISODE_CONTRACT",
            },
            {
                "question": "CROSS_REGIME_GENERALIZATION",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": "CURRENT_SCOPE_BELOW_480_AND_THREE_REGIME_DESIGN",
            },
            {
                "question": "ASSOCIATION_FAMILY_DISCOVERY",
                "status": "UNKNOWN_NOT_EVALUATED",
                "claim_scope": "NO_CLAIM",
                "reason": "CURRENT_SCOPE_BELOW_SMALLEST_FROZEN_SAMPLE_77",
            },
        ],
        "forecast_probability_output": None,
        "brier_log_ece_output": None,
        "ev_output": None,
        "cost_after_return_output": None,
        "local_completion_may_promote_market_claim": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(status, STATUS_DIGEST_FIELD)


def verify_v32_current_scope_evaluation_status(
    status: Mapping[str, Any],
    evaluation_contract: Mapping[str, Any],
    association_preregistration: Mapping[str, Any],
) -> str:
    """Rebuild a status so a re-digested overclaim still fails closed."""

    if not isinstance(status, Mapping):
        raise V32EvaluationContractError("V32_EVALUATION_STATUS_INVALID")
    try:
        supplied = verify_self_digest(status, STATUS_DIGEST_FIELD)
        rebuilt = build_v32_current_scope_evaluation_status(
            evaluation_contract=evaluation_contract,
            association_preregistration=association_preregistration,
            accepted_analysis_cycle_count=status[
                "accepted_analysis_cycle_count"
            ],
            terminal_outcome_schedule_count=status[
                "terminal_outcome_schedule_count"
            ],
            assessed_at=status["assessed_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32EvaluationContractError):
            raise
        raise V32EvaluationContractError(
            "V32_EVALUATION_STATUS_INVALID"
        ) from exc
    if dict(status) != rebuilt or supplied != rebuilt[STATUS_DIGEST_FIELD]:
        raise V32EvaluationContractError(
            "V32_EVALUATION_STATUS_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "CALIBRATION_MIN_PROSPECTIVE_FORECASTS",
    "COST_AFTER_RETURN_MIN_COMPLETED_EPISODES",
    "CROSS_REGIME_MIN_DECISIONS_PER_REGIME",
    "CROSS_REGIME_MIN_REGIMES",
    "CROSS_REGIME_MIN_TOTAL_DECISIONS",
    "DIGEST_FIELD",
    "PILOT_OUTCOME_SCHEDULE_COUNT",
    "PREDICTIVE_INCREMENT_MIN_DECISIONS",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "STATUS_SCHEMA_ID",
    "STATUS_DIGEST_FIELD",
    "V32EvaluationContractError",
    "build_v32_current_scope_evaluation_status",
    "build_v32_evaluation_contract",
    "verify_v32_current_scope_evaluation_status",
    "verify_v32_evaluation_contract",
]
