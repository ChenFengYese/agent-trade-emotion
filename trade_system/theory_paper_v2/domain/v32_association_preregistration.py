"""Frozen V3.2 association universe for the 15-minute process pilot.

This pure Domain contract fixes the complete finite search universe before any
pilot outcome is read.  It does not fetch data, calculate an association, or
promote an association into causality, a forecast probability, EV, or action.

The 144 candidates are the Cartesian product of twelve sentiment axes, two
target types, two closed point-in-time windows, and three forward horizons.
The two target families are dependent by construction, so each fixed family
uses Benjamini--Yekutieli FDR with Holm confirmatory FWER.  Ordinary BH is not
an allowed post-hoc alternative.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest


class V32AssociationPreregistrationError(ValueError):
    """The V3.2 association pre-registration failed closed."""


SCHEMA_ID = "theory_paper_v2_v32_association_preregistration_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "association_preregistration_digest"
INSTRUMENT_ID = "BTC-USDT-SWAP"
PILOT_ID = "V32_DYNAMIC_AGGRESSIVE_BTCUSDT_15M_PROCESS_PILOT"
PILOT_ANALYSIS_CYCLE_CAP = 16
CANDIDATE_COUNT = 144

V32_ASSOCIATION_AXES = (
    "PRICE_DIRECTIONAL_PRESSURE",
    "STRUCTURE_PERSISTENCE",
    "PARTICIPATION_AND_ACTIVE_FLOW",
    "CROWDING_DIRECTION",
    "LEVERAGE_CHANGE",
    "FORCED_DELEVERAGING_PRESSURE",
    "LIQUIDITY_RESILIENCE",
    "VOLATILITY_AND_TAIL_STRESS",
    "EVENT_AND_NARRATIVE_REACTION",
    "ATTENTION_AND_AUDIENCE_RESPONSE",
    "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
    "TIMEFRAME_COHERENCE",
)

_TARGETS = (
    {
        "target_id": "DIRECTION",
        "family_id": "V32_AXIS_TO_FORWARD_DIRECTION",
        "source_variable": "V32_SENTIMENT_AXIS_SIGNED_ORDINAL_VALUE",
        "source_transform": "SIGNED_ORDINAL_MINUS2_TO_PLUS2_NO_IMPUTATION_V1",
        "target_variable": "BTC_USDT_SWAP_FORWARD_LOG_MARK_RETURN",
        "target_transform": "LOG_MARK_T_PLUS_H_DIV_MARK_T_V1",
        "estimand": "KENDALL_TAU_B_AXIS_LEVEL_VS_FORWARD_SIGNED_RETURN",
    },
    {
        "target_id": "MAGNITUDE",
        "family_id": "V32_AXIS_TO_FORWARD_MAGNITUDE",
        "source_variable": "V32_SENTIMENT_AXIS_ABSOLUTE_ORDINAL_VALUE",
        "source_transform": "ABS_ORDINAL_ZERO_TO2_NO_IMPUTATION_V1",
        "target_variable": "BTC_USDT_SWAP_FORWARD_ABSOLUTE_LOG_MARK_RETURN",
        "target_transform": "ABS_LOG_MARK_T_PLUS_H_DIV_MARK_T_V1",
        "estimand": (
            "KENDALL_TAU_B_AXIS_MAGNITUDE_VS_FORWARD_ABSOLUTE_RETURN"
        ),
    },
)

# Both windows count eligible 15-minute source/target pairs, not wall-clock bars.
# The minimum sample is the exact ceiling of 80% coverage.
_WINDOWS = (
    {
        "window_id": "LAST_96_ELIGIBLE_CLOSED_15M_PAIRS",
        "eligible_pair_count": 96,
        "minimum_observed_sample": 77,
    },
    {
        "window_id": "LAST_384_ELIGIBLE_CLOSED_15M_PAIRS",
        "eligible_pair_count": 384,
        "minimum_observed_sample": 308,
    },
)

_HORIZONS = (
    {"horizon_id": "15M", "value": 15, "unit": "MINUTE"},
    {"horizon_id": "1H", "value": 60, "unit": "MINUTE"},
    {"horizon_id": "4H", "value": 240, "unit": "MINUTE"},
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V32AssociationPreregistrationError(code)
    return value.strip()


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V32AssociationPreregistrationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32AssociationPreregistrationError(code) from exc
    if parsed.tzinfo is None:
        raise V32AssociationPreregistrationError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _candidate_id(
    *, target_id: str, axis: str, window_size: int, horizon_id: str
) -> str:
    return f"ASSOC_V32:{target_id}:{axis}:W{window_size}:H{horizon_id}"


def _build_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for target in _TARGETS:
        for axis in V32_ASSOCIATION_AXES:
            for window in _WINDOWS:
                for horizon in _HORIZONS:
                    candidates.append(
                        {
                            "candidate_id": _candidate_id(
                                target_id=target["target_id"],
                                axis=axis,
                                window_size=window["eligible_pair_count"],
                                horizon_id=horizon["horizon_id"],
                            ),
                            "family_id": target["family_id"],
                            "source_axis": axis,
                            "source_variable": target["source_variable"],
                            "source_transform": target["source_transform"],
                            "target_id": target["target_id"],
                            "target_variable": target["target_variable"],
                            "target_transform": target["target_transform"],
                            "estimand": target["estimand"],
                            "association_type": "PREDICTIVE_LEAD_CANDIDATE",
                            "temporal_direction": "SOURCE_AT_T_LEADS_TARGET_AT_T_PLUS_H",
                            "alternative": "TWO_SIDED",
                            "horizon": {
                                "horizon_id": horizon["horizon_id"],
                                "value": horizon["value"],
                                "unit": horizon["unit"],
                                "source_state": "CLOSED_15M_PIT_STATE_AT_T",
                                "target_state": "PUBLIC_MARK_AT_OR_AFTER_T_PLUS_H",
                                "target_must_be_matured_before_evaluation": True,
                            },
                            "lag": {
                                "source_lag_steps": 0,
                                "forward_target_lag_minutes": horizon["value"],
                                "selection": "FROZEN_EQUAL_TO_OUTCOME_HORIZON",
                                "post_freeze_change": "FORBIDDEN",
                            },
                            "window": {
                                "window_id": window["window_id"],
                                "selection": (
                                    "LAST_N_ELIGIBLE_PIT_SOURCE_TARGET_PAIRS_"
                                    "AVAILABLE_BY_EVALUATION_CUTOFF"
                                ),
                                "eligible_pair_count": window[
                                    "eligible_pair_count"
                                ],
                                "minimum_observed_sample": window[
                                    "minimum_observed_sample"
                                ],
                                "source_timeframe": "15M",
                                "source_bar_state": "CLOSED_ONLY",
                                "target_must_be_closed_and_available": True,
                            },
                            "interpretation_boundary": (
                                "ASSOCIATION_NOT_STRUCTURAL_CAUSALITY"
                            ),
                        }
                    )
    return sorted(candidates, key=lambda item: item["candidate_id"])


def _build_families(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = []
    for target in _TARGETS:
        candidate_ids = sorted(
            candidate["candidate_id"]
            for candidate in candidates
            if candidate["family_id"] == target["family_id"]
        )
        families.append(
            {
                "family_id": target["family_id"],
                "target_id": target["target_id"],
                "candidate_ids": candidate_ids,
                "family_size": len(candidate_ids),
                "family_is_fixed_before_outcomes": True,
                "family_dependency": (
                    "DEPENDENT_OVERLAPPING_AXES_WINDOWS_AND_HORIZONS"
                ),
                "fdr_procedure": "BENJAMINI_YEKUTIELI_STEP_UP_V1",
                "fdr_q": "0.05",
                "dependency_assumption": "ARBITRARY_DEPENDENCE_ALLOWED",
                "ordinary_bh_enabled": False,
                "ordinary_bh_substitution": "FORBIDDEN",
                "confirmatory_fwer_procedure": "HOLM_STEP_DOWN_V1",
                "confirmatory_fwer_alpha": "0.05",
                "alternative": "TWO_SIDED",
                "incomplete_family_result": (
                    "UNKNOWN_NOT_EVALUATED_NO_MULTIPLICITY_CLAIM"
                ),
                "p_value_is_forecast_probability": False,
            }
        )
    return sorted(families, key=lambda item: item["family_id"])


def build_v32_association_preregistration(
    *, run_scope_id: str, frozen_at: str, instrument_id: str = INSTRUMENT_ID
) -> dict[str, Any]:
    """Build the exact 144-candidate V3.2 pre-registration."""

    scope = _text(run_scope_id, "V32_ASSOCIATION_RUN_SCOPE_INVALID")
    frozen = _time_text(_timestamp(frozen_at, "V32_ASSOCIATION_TIME_INVALID"))
    instrument = _text(instrument_id, "V32_ASSOCIATION_INSTRUMENT_INVALID")
    if instrument != INSTRUMENT_ID:
        raise V32AssociationPreregistrationError(
            "V32_ASSOCIATION_INSTRUMENT_OUT_OF_SCOPE"
        )

    candidates = _build_candidates()
    families = _build_families(candidates)
    if len(candidates) != CANDIDATE_COUNT:
        raise V32AssociationPreregistrationError(
            "V32_ASSOCIATION_INTERNAL_CANDIDATE_COUNT_INVALID"
        )
    summary = self_digest(
        {
            "axis_count": len(V32_ASSOCIATION_AXES),
            "target_count": len(_TARGETS),
            "window_count": len(_WINDOWS),
            "horizon_count": len(_HORIZONS),
            "candidate_count": len(candidates),
            "family_count": len(families),
            "candidate_ids_digest": canonical_digest(
                [candidate["candidate_id"] for candidate in candidates]
            ),
            "family_registry_digest": canonical_digest(families),
            "cartesian_product_rule": "12_AXES_X_2_TARGETS_X_2_WINDOWS_X_3_HORIZONS",
            "pilot_cycle_cap": PILOT_ANALYSIS_CYCLE_CAP,
            "pilot_association_eligibility": (
                "UNKNOWN_NOT_EVALUATED_INSUFFICIENT_SAMPLE"
            ),
        },
        "registry_summary_digest",
    )

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": scope,
        "frozen_at": frozen,
        "instrument_id": instrument,
        "pilot_id": PILOT_ID,
        "pilot_analysis_cycle_cap": PILOT_ANALYSIS_CYCLE_CAP,
        "registry_status": "FROZEN_COMPLETE_FINITE_UNIVERSE",
        "must_precede_first_pilot_outcome": True,
        "candidate_search_after_freeze": "FORBIDDEN",
        "candidate_addition_policy": (
            "NEW_VERSION_NEW_PREREGISTRATION_AND_NEW_PROSPECTIVE_SCOPE_REQUIRED"
        ),
        "axis_registry": list(V32_ASSOCIATION_AXES),
        "target_registry": [dict(target) for target in _TARGETS],
        "window_registry": [dict(window) for window in _WINDOWS],
        "horizon_registry": [dict(horizon) for horizon in _HORIZONS],
        "data_contract": {
            "public_data_only": True,
            "point_in_time_required": True,
            "closed_source_state_only": True,
            "matured_target_only": True,
            "available_at_must_not_exceed_evaluation_cutoff": True,
            "future_data_forbidden": True,
            "duplicate_pair_forbidden": True,
            "imputation": "FORBIDDEN",
            "unknown_is_zero": False,
            "pairing": "EXACT_SOURCE_TIME_PLUS_FROZEN_HORIZON",
        },
        "missingness_contract": {
            "method": "PAIRWISE_COMPLETE_WITHOUT_IMPUTATION",
            "maximum_missing_fraction": "0.2",
            "minimum_observed_sample_is_window_specific": True,
            "insufficient_or_excess_missing_result": "UNKNOWN_NOT_EVALUATED",
            "zero_variance_or_all_ties_result": "UNKNOWN_NOT_EVALUATED",
            "unknown_never_enters_multiplicity_as_zero_or_one": True,
        },
        "estimator_contract": {
            "estimator": "KENDALL_TAU_B_MOVING_BLOCK_BOOTSTRAP_V1",
            "effect_scale": "KENDALL_TAU_B",
            "effect_bounds": {"lower": "-1", "upper": "1"},
            "ties": "KENDALL_TAU_B_EXPLICIT_TIE_CORRECTION",
            "interval": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95_V1",
            "interval_confidence_level": "0.95",
            "bootstrap_resamples": 10000,
            "bootstrap_seed_rule": (
                "FIRST_64_BITS_SHA256_OF_CANDIDATE_ID_AND_EVALUATION_CUTOFF"
            ),
            "block_length_rule": "CEILING_CUBE_ROOT_OBSERVED_SAMPLE",
            "serial_and_overlap_dependence_preserved": True,
            "p_value": "TWO_SIDED_NULL_CENTERED_MOVING_BLOCK_BOOTSTRAP_V1",
            "p_value_is_forecast_probability": False,
            "implementation_status": "CONTRACT_ONLY_REQUIRES_TRUSTED_RECEIPT",
        },
        "multiplicity_contract": {
            "family_partition": "BY_TARGET_TYPE_DIRECTION_OR_MAGNITUDE",
            "families_are_dependent": True,
            "primary_fdr": "BENJAMINI_YEKUTIELI_STEP_UP_V1",
            "primary_fdr_q": "0.05",
            "confirmatory_fwer": "HOLM_STEP_DOWN_V1",
            "confirmatory_fwer_alpha": "0.05",
            "ordinary_bh_enabled": False,
            "post_outcome_family_window_horizon_or_method_change": "FORBIDDEN",
        },
        "families": families,
        "candidates": candidates,
        "registry_summary": summary,
        "downstream_boundary": {
            "pilot_use": "SHORT_WINDOW_DESCRIPTIVE_RESEARCH_ONLY",
            "hypothesis_discovery_requires_new_prospective_revision": True,
            "action_input": False,
            "probability_cloud_input": False,
            "causal_claim": False,
            "predictive_validity_claim": False,
            "profitability_claim": False,
            "ev_allowed": False,
        },
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_association_preregistration(
    document: Mapping[str, Any],
) -> str:
    """Rebuild the whole registry, rejecting drift even after re-digesting."""

    if not isinstance(document, Mapping):
        raise V32AssociationPreregistrationError(
            "V32_ASSOCIATION_DOCUMENT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, DIGEST_FIELD
        )
        summary_digest = verify_self_digest(
            document["registry_summary"], "registry_summary_digest"
        )
        rebuilt = build_v32_association_preregistration(
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            instrument_id=document["instrument_id"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32AssociationPreregistrationError):
            raise
        raise V32AssociationPreregistrationError(
            "V32_ASSOCIATION_DOCUMENT_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt[DIGEST_FIELD]
        or summary_digest
        != rebuilt["registry_summary"]["registry_summary_digest"]
    ):
        raise V32AssociationPreregistrationError(
            "V32_ASSOCIATION_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "CANDIDATE_COUNT",
    "DIGEST_FIELD",
    "INSTRUMENT_ID",
    "PILOT_ANALYSIS_CYCLE_CAP",
    "PILOT_ID",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "V32AssociationPreregistrationError",
    "V32_ASSOCIATION_AXES",
    "build_v32_association_preregistration",
    "verify_v32_association_preregistration",
]
