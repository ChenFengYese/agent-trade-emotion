"""Frozen V3.1 successor association universe and multiplicity receipts.

This pure Domain module closes one narrow design gap: an association result may
not be called pre-registered unless the complete candidate universe, transforms,
closed-data windows, lags, missingness rules, estimator contract, and
multiplicity family were sealed before outcomes were observed.

The module does not fetch data and does not estimate market relationships.  It
admits estimator receipts and performs only deterministic family-level
Benjamini-Yekutieli FDR and Holm FWER correction.  BY is the conservative
default because the axis candidates are dependent.  Ordinary BH is disabled
unless a future version freezes independent/PRDS evidence before outcomes.
Test p-values are never forecast probabilities, and no result from this module
is an action, probability-cloud, causal, EV, or portfolio input.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)


class V31AssociationPreregistrationError(ValueError):
    """A successor association pre-registration failed closed."""


SCHEMA_ID = "theory_paper_v2_v31_association_preregistration_v2"
SCHEMA_VERSION = "2.0.0"
MULTIPLICITY_RECEIPT_SCHEMA_ID = (
    "theory_paper_v2_v31_by_fdr_holm_fwer_family_receipt_v2"
)

INSTRUMENT_ID = "BTC-USDT-SWAP"
CURRENT_EXPERIMENT_CYCLE_CAP = 8
FDR_Q = Decimal("0.05")
FWER_ALPHA = Decimal("0.05")
INTERVAL_CONFIDENCE_LEVEL = Decimal("0.95")

V31_SENTIMENT_AXES = (
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

_FAMILY_DEFINITIONS = (
    {
        "family_id": "BTC_SWAP_AXIS_TO_FORWARD_DIRECTION_V2",
        "target_variable": "BTC_USDT_SWAP_FORWARD_LOG_RETURN",
        "target_transform": "LOG_MARK_T_PLUS_H_DIV_MARK_T_V1",
        "estimand": "KENDALL_TAU_B_AXIS_LEVEL_VS_FORWARD_SIGNED_RETURN",
    },
    {
        "family_id": "BTC_SWAP_AXIS_TO_FORWARD_MAGNITUDE_V2",
        "target_variable": "BTC_USDT_SWAP_FORWARD_ABSOLUTE_LOG_RETURN",
        "target_transform": "ABS_LOG_MARK_T_PLUS_H_DIV_MARK_T_V1",
        "estimand": "KENDALL_TAU_B_AXIS_MAGNITUDE_VS_FORWARD_ABSOLUTE_RETURN",
    },
)

_WINDOWS = (
    {
        "window_id": "LAST_168_ELIGIBLE_CLOSED_1H_PAIRS",
        "eligible_pair_count": 168,
        "minimum_observed_sample": 135,
    },
    {
        "window_id": "LAST_720_ELIGIBLE_CLOSED_1H_PAIRS",
        "eligible_pair_count": 720,
        "minimum_observed_sample": 576,
    },
)

_LAG_HOURS = (1, 4)
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

_ALLOWED_UNKNOWN_REASONS = frozenset(
    {
        "INSUFFICIENT_SAMPLE",
        "MISSINGNESS_ABOVE_LIMIT",
        "ZERO_VARIANCE_OR_ALL_TIES",
        "ESTIMATOR_NOT_IMPLEMENTED",
        "INTERVAL_NOT_IDENTIFIED",
        "PIT_OR_CLOCK_INVALID",
        "SOURCE_UNAVAILABLE",
        "REGIME_COVERAGE_INSUFFICIENT",
    }
)

_RESULT_FIELDS = frozenset(
    {
        "candidate_id",
        "status",
        "eligible_sample_count",
        "observed_sample_count",
        "missing_sample_count",
        "effect_size",
        "interval",
        "p_value",
        "unknown_reason",
        "upstream_receipt_digest",
    }
)
_INTERVAL_FIELDS = frozenset(
    {"kind", "lower", "upper", "confidence_level"}
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31AssociationPreregistrationError(code)
    return value.strip()


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31AssociationPreregistrationError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31AssociationPreregistrationError(code) from exc
    if parsed.tzinfo is None:
        raise V31AssociationPreregistrationError(code)
    return parsed.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _integer(value: Any, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise V31AssociationPreregistrationError(code)
    return value


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise V31AssociationPreregistrationError(code)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V31AssociationPreregistrationError(code) from exc
    if not parsed.is_finite():
        raise V31AssociationPreregistrationError(code)
    return parsed


def _decimal_text(value: Decimal) -> str:
    """Render computed Decimals without ambient-context rounding."""

    required = len(value.as_tuple().digits) + abs(value.as_tuple().exponent) + 10
    with localcontext() as context:
        context.prec = max(100, required)
        return canonical_decimal(value)


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31AssociationPreregistrationError(code)
    return value


def _candidate_id(
    *, family_id: str, axis: str, lag_hours: int, eligible_pair_count: int
) -> str:
    family_token = "DIR" if "DIRECTION" in family_id else "MAG"
    return (
        f"ASSOC_V2:{family_token}:{axis}:"
        f"L{lag_hours}H:W{eligible_pair_count}"
    )


def _build_candidate_registry() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for family in _FAMILY_DEFINITIONS:
        for axis in V31_SENTIMENT_AXES:
            for lag_hours in _LAG_HOURS:
                for window in _WINDOWS:
                    candidates.append(
                        {
                            "candidate_id": _candidate_id(
                                family_id=family["family_id"],
                                axis=axis,
                                lag_hours=lag_hours,
                                eligible_pair_count=window[
                                    "eligible_pair_count"
                                ],
                            ),
                            "family_id": family["family_id"],
                            "source_axis": axis,
                            "source_variable": (
                                "V31_SENTIMENT_AXIS_ORDINAL_VALUE"
                                if "DIRECTION" in family["family_id"]
                                else "V31_SENTIMENT_AXIS_ABSOLUTE_ORDINAL_VALUE"
                            ),
                            "source_transform": (
                                "SIGNED_ORDINAL_MINUS2_TO_PLUS2_NO_IMPUTATION_V1"
                                if "DIRECTION" in family["family_id"]
                                else "ABS_ORDINAL_ZERO_TO2_NO_IMPUTATION_V1"
                            ),
                            "target_variable": family["target_variable"],
                            "target_transform": family["target_transform"],
                            "estimand": family["estimand"],
                            "association_type": "PREDICTIVE_LEAD",
                            "interpretation_boundary": (
                                "PREDICTIVE_NOT_STRUCTURAL_CAUSAL"
                            ),
                            "temporal_direction": "SOURCE_LEADS_TARGET",
                            "alternative": "TWO_SIDED",
                            "lag": {
                                "value": lag_hours,
                                "unit": "HOUR",
                                "source_time": "CLOSED_1H_STATE_AT_T",
                                "target_time": f"MARK_AT_T_PLUS_{lag_hours}H",
                            },
                            "window": {
                                "window_id": window["window_id"],
                                "selection": (
                                    "LAST_N_ELIGIBLE_POINT_IN_TIME_PAIRS_"
                                    "BEFORE_EVALUATION"
                                ),
                                "eligible_pair_count": window[
                                    "eligible_pair_count"
                                ],
                                "minimum_observed_sample": window[
                                    "minimum_observed_sample"
                                ],
                                "timeframe": "1H",
                                "bar_state": "CLOSED_ONLY",
                                "target_must_be_closed_and_available": True,
                            },
                        }
                    )
    return sorted(candidates, key=lambda item: item["candidate_id"])


def _build_families(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    families: list[dict[str, Any]] = []
    for definition in _FAMILY_DEFINITIONS:
        family_id = definition["family_id"]
        candidate_ids = sorted(
            item["candidate_id"]
            for item in candidates
            if item["family_id"] == family_id
        )
        harmonic = _harmonic_number(len(candidate_ids))
        families.append(
            {
                "family_id": family_id,
                "candidate_ids": candidate_ids,
                "family_size": len(candidate_ids),
                "fdr_procedure": "BENJAMINI_YEKUTIELI_STEP_UP_V1",
                "error_rate": "FALSE_DISCOVERY_RATE",
                "q": _decimal_text(FDR_Q),
                "harmonic_constant_c_m": _decimal_text(harmonic),
                "fdr_rank_threshold_rule": "I_TIMES_Q_DIV_M_TIMES_C_M",
                "dependency_assumption": "ARBITRARY_DEPENDENCE_ALLOWED",
                "ordinary_bh_exception": {
                    "enabled": False,
                    "requires": (
                        "NEW_PREREGISTRATION_VERSION_WITH_PRE_OUTCOME_"
                        "INDEPENDENCE_OR_PRDS_PROOF"
                    ),
                },
                "confirmatory_fwer_procedure": "HOLM_STEP_DOWN_V1",
                "confirmatory_fwer_alpha": _decimal_text(FWER_ALPHA),
                "holm_rank_threshold_rule": "ALPHA_DIV_M_MINUS_I_PLUS_1",
                "alternative": "TWO_SIDED",
                "family_is_fixed_before_outcomes": True,
                "missing_candidate_policy": (
                    "ENTIRE_FAMILY_UNKNOWN_NO_DISCOVERY_CLAIM"
                ),
                "p_value_interpretation": (
                    "TEST_STATISTIC_TAIL_AREA_NOT_FORECAST_PROBABILITY"
                ),
            }
        )
    return sorted(families, key=lambda item: item["family_id"])


def build_v31_association_preregistration_v2(
    *, run_scope_id: str, frozen_at: str, instrument_id: str = INSTRUMENT_ID
) -> dict[str, Any]:
    """Seal the complete finite 96-candidate successor search universe."""

    scope = _text(run_scope_id, "ASSOCIATION_PREREG_RUN_SCOPE_INVALID")
    frozen = _time_text(_timestamp(frozen_at, "ASSOCIATION_PREREG_TIME_INVALID"))
    instrument = _text(
        instrument_id, "ASSOCIATION_PREREG_INSTRUMENT_INVALID"
    )
    if instrument != INSTRUMENT_ID:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_PREREG_INSTRUMENT_OUT_OF_SCOPE"
        )
    candidates = _build_candidate_registry()
    families = _build_families(candidates)
    candidate_ids = [item["candidate_id"] for item in candidates]
    family_summaries = [
        {"family_id": item["family_id"], "family_size": item["family_size"]}
        for item in families
    ]
    summary = self_digest(
        {
            "candidate_count": len(candidates),
            "family_count": len(families),
            "candidate_ids_digest": canonical_digest(candidate_ids),
            "family_summaries": family_summaries,
            "source_axis_count": len(V31_SENTIMENT_AXES),
            "lag_hours": list(_LAG_HOURS),
            "eligible_pair_windows": [
                item["eligible_pair_count"] for item in _WINDOWS
            ],
            "current_experiment_cycle_cap": CURRENT_EXPERIMENT_CYCLE_CAP,
            "current_experiment_eligibility": (
                "NOT_EVALUATED_INSUFFICIENT_SAMPLE"
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
        "registry_status": "FROZEN_COMPLETE_FINITE_UNIVERSE",
        "candidate_search": "FORBIDDEN_AFTER_FREEZE",
        "candidate_addition_policy": (
            "NEW_VERSION_AND_NEW_PROSPECTIVE_EXPERIMENT_REQUIRED"
        ),
        "allowed_variables": {
            "source_axes": list(V31_SENTIMENT_AXES),
            "source_representations": [
                "V31_SENTIMENT_AXIS_ORDINAL_VALUE",
                "V31_SENTIMENT_AXIS_ABSOLUTE_ORDINAL_VALUE",
            ],
            "targets": [
                item["target_variable"] for item in _FAMILY_DEFINITIONS
            ],
            "unregistered_variables_forbidden": True,
        },
        "data_contract": {
            "public_data_only": True,
            "point_in_time_required": True,
            "closed_data_only": True,
            "future_data_forbidden": True,
            "imputation": "FORBIDDEN",
            "unknown_is_zero": False,
            "pairing": "EXACT_TIMESTAMP_AND_LAG_CONTRACT",
            "duplicate_pair_forbidden": True,
        },
        "estimator_contract": {
            "estimator": "KENDALL_TAU_B_MOVING_BLOCK_BOOTSTRAP_V1",
            "implementation_status": "CONTRACT_ONLY_REQUIRES_TRUSTED_RECEIPT",
            "effect_scale": "KENDALL_TAU_B",
            "effect_bounds": {"lower": "-1", "upper": "1"},
            "interval": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95_V1",
            "interval_confidence_level": _decimal_text(
                INTERVAL_CONFIDENCE_LEVEL
            ),
            "bootstrap_resamples": 10000,
            "bootstrap_seed_rule": (
                "FIRST_64_BITS_OF_SHA256_CANDIDATE_ID_AND_WINDOW_END"
            ),
            "block_length_rule": "CEILING_CUBE_ROOT_OBSERVED_SAMPLE",
            "serial_dependence_preserved": True,
            "ties": "KENDALL_TAU_B_EXPLICIT_TIE_CORRECTION",
            "p_value": "TWO_SIDED_NULL_CENTERED_BLOCK_BOOTSTRAP_V1",
            "p_value_is_forecast_probability": False,
        },
        "missingness_contract": {
            "method": "PAIRWISE_COMPLETE_WITHOUT_IMPUTATION",
            "maximum_missing_fraction": "0.2",
            "minimum_sample_is_candidate_specific": True,
            "insufficient_or_excess_missing_result": "UNKNOWN_NOT_EVALUATED",
            "zero_variance_or_all_ties_result": "UNKNOWN_NOT_EVALUATED",
                "unknown_never_enters_multiplicity_as_zero_or_one": True,
        },
        "families": families,
        "candidates": candidates,
        "registry_summary": summary,
        "downstream_boundary": {
            "use": "DESCRIPTIVE_END_OF_RUN_RESEARCH_ONLY",
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
    return self_digest(document, "association_preregistration_digest")


def verify_v31_association_preregistration_v2(
    document: Mapping[str, Any],
) -> str:
    """Reconstruct the fixed universe and reject any field or digest drift."""

    if not isinstance(document, Mapping):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_PREREG_DOCUMENT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            document, "association_preregistration_digest"
        )
        rebuilt = build_v31_association_preregistration_v2(
            run_scope_id=document["run_scope_id"],
            frozen_at=document["frozen_at"],
            instrument_id=document["instrument_id"],
        )
        summary_digest = verify_self_digest(
            document["registry_summary"], "registry_summary_digest"
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31AssociationPreregistrationError):
            raise
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_PREREG_DOCUMENT_INVALID"
        ) from exc
    if (
        dict(document) != rebuilt
        or supplied != rebuilt["association_preregistration_digest"]
        or summary_digest
        != rebuilt["registry_summary"]["registry_summary_digest"]
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_PREREG_RECONSTRUCTION_MISMATCH"
        )
    return supplied


def _candidate_map(
    preregistration: Mapping[str, Any], family_id: str
) -> tuple[dict[str, Mapping[str, Any]], Mapping[str, Any]]:
    verify_v31_association_preregistration_v2(preregistration)
    family_matches = [
        item
        for item in preregistration["families"]
        if item["family_id"] == family_id
    ]
    if len(family_matches) != 1:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_BH_FAMILY_INVALID"
        )
    family = family_matches[0]
    candidate_map = {
        item["candidate_id"]: item
        for item in preregistration["candidates"]
        if item["family_id"] == family_id
    }
    return candidate_map, family


def _normalize_interval(value: Any, *, effect: Decimal) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _INTERVAL_FIELDS:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_INTERVAL_SCHEMA_INVALID"
        )
    if value.get("kind") != "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95_V1":
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_INTERVAL_KIND_INVALID"
        )
    lower = _decimal(
        value.get("lower"), "ASSOCIATION_RESULT_INTERVAL_NUMBER_INVALID"
    )
    upper = _decimal(
        value.get("upper"), "ASSOCIATION_RESULT_INTERVAL_NUMBER_INVALID"
    )
    confidence = _decimal(
        value.get("confidence_level"),
        "ASSOCIATION_RESULT_INTERVAL_CONFIDENCE_INVALID",
    )
    if (
        lower < -1
        or upper > 1
        or lower > effect
        or effect > upper
        or confidence != INTERVAL_CONFIDENCE_LEVEL
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_INTERVAL_INVALID"
        )
    return {
        "kind": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95_V1",
        "lower": _decimal_text(lower),
        "upper": _decimal_text(upper),
        "confidence_level": _decimal_text(confidence),
    }


def _normalize_result(
    value: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RESULT_FIELDS:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_SCHEMA_INVALID"
        )
    if value.get("candidate_id") != candidate["candidate_id"]:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_CANDIDATE_MISMATCH"
        )
    status = value.get("status")
    if status not in {"EVALUATED", "UNKNOWN_NOT_EVALUATED"}:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_STATUS_INVALID"
        )
    eligible = _integer(
        value.get("eligible_sample_count"),
        "ASSOCIATION_RESULT_SAMPLE_INVALID",
    )
    observed = _integer(
        value.get("observed_sample_count"),
        "ASSOCIATION_RESULT_SAMPLE_INVALID",
    )
    missing = _integer(
        value.get("missing_sample_count"),
        "ASSOCIATION_RESULT_SAMPLE_INVALID",
    )
    planned = candidate["window"]["eligible_pair_count"]
    minimum = candidate["window"]["minimum_observed_sample"]
    if observed + missing != eligible or eligible > planned:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_SAMPLE_ACCOUNTING_INVALID"
        )
    upstream_digest = _digest(
        value.get("upstream_receipt_digest"),
        "ASSOCIATION_RESULT_UPSTREAM_DIGEST_INVALID",
    )
    if status == "EVALUATED":
        if eligible != planned or observed < minimum or 5 * missing > eligible:
            raise V31AssociationPreregistrationError(
                "ASSOCIATION_RESULT_EVALUATION_GATE_NOT_MET"
            )
        effect = _decimal(
            value.get("effect_size"), "ASSOCIATION_RESULT_EFFECT_INVALID"
        )
        p_value = _decimal(
            value.get("p_value"), "ASSOCIATION_RESULT_P_VALUE_INVALID"
        )
        if effect < -1 or effect > 1 or p_value < 0 or p_value > 1:
            raise V31AssociationPreregistrationError(
                "ASSOCIATION_RESULT_NUMBER_OUT_OF_RANGE"
            )
        if value.get("unknown_reason") is not None:
            raise V31AssociationPreregistrationError(
                "ASSOCIATION_RESULT_UNKNOWN_REASON_FORBIDDEN"
            )
        interval = _normalize_interval(value.get("interval"), effect=effect)
        return {
            "candidate_id": candidate["candidate_id"],
            "status": status,
            "eligible_sample_count": eligible,
            "observed_sample_count": observed,
            "missing_sample_count": missing,
            "effect_size": _decimal_text(effect),
            "interval": interval,
            "p_value": _decimal_text(p_value),
            "unknown_reason": None,
            "upstream_receipt_digest": upstream_digest,
        }

    reason = value.get("unknown_reason")
    if reason not in _ALLOWED_UNKNOWN_REASONS:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_UNKNOWN_REASON_INVALID"
        )
    if any(
        value.get(field) is not None
        for field in ("effect_size", "interval", "p_value")
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_UNKNOWN_NUMERIC_RESULT_FORBIDDEN"
        )
    if reason == "INSUFFICIENT_SAMPLE" and observed >= minimum:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_UNKNOWN_REASON_INCONSISTENT"
        )
    if reason == "MISSINGNESS_ABOVE_LIMIT" and (
        eligible == 0 or 5 * missing <= eligible
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_UNKNOWN_REASON_INCONSISTENT"
        )
    return {
        "candidate_id": candidate["candidate_id"],
        "status": status,
        "eligible_sample_count": eligible,
        "observed_sample_count": observed,
        "missing_sample_count": missing,
        "effect_size": None,
        "interval": None,
        "p_value": None,
        "unknown_reason": reason,
        "upstream_receipt_digest": upstream_digest,
    }


def _harmonic_number(size: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return sum(
            (Decimal(1) / Decimal(index) for index in range(1, size + 1)),
            Decimal(0),
        )


def _by_adjustments(
    evaluated: Sequence[Mapping[str, Any]], *, family_size: int
) -> tuple[
    dict[str, Decimal], set[str], int | None, Decimal | None, Decimal
]:
    ranked = sorted(
        evaluated,
        key=lambda item: (
            _decimal(item["p_value"], "ASSOCIATION_RESULT_P_VALUE_INVALID"),
            item["candidate_id"],
        ),
    )
    harmonic = _harmonic_number(family_size)
    critical_rank: int | None = None
    critical_p: Decimal | None = None
    for rank, item in enumerate(ranked, start=1):
        p_value = _decimal(
            item["p_value"], "ASSOCIATION_RESULT_P_VALUE_INVALID"
        )
        with localcontext() as context:
            context.prec = 50
            threshold = (
                FDR_Q * Decimal(rank) / (Decimal(family_size) * harmonic)
            )
        if p_value <= threshold:
            critical_rank = rank
            critical_p = p_value
    rejected = {
        item["candidate_id"]
        for rank, item in enumerate(ranked, start=1)
        if critical_rank is not None and rank <= critical_rank
    }
    adjusted: dict[str, Decimal] = {}
    running = Decimal(1)
    for rank in range(len(ranked), 0, -1):
        item = ranked[rank - 1]
        p_value = _decimal(
            item["p_value"], "ASSOCIATION_RESULT_P_VALUE_INVALID"
        )
        with localcontext() as context:
            context.prec = 50
            scaled = min(
                Decimal(1),
                p_value * Decimal(family_size) * harmonic / Decimal(rank),
            )
        running = min(running, scaled)
        adjusted[item["candidate_id"]] = running
    return adjusted, rejected, critical_rank, critical_p, harmonic


def _holm_adjustments(
    evaluated: Sequence[Mapping[str, Any]], *, family_size: int
) -> tuple[dict[str, Decimal], set[str]]:
    ranked = sorted(
        evaluated,
        key=lambda item: (
            _decimal(item["p_value"], "ASSOCIATION_RESULT_P_VALUE_INVALID"),
            item["candidate_id"],
        ),
    )
    adjusted: dict[str, Decimal] = {}
    running = Decimal(0)
    rejection_open = True
    rejected: set[str] = set()
    for rank, item in enumerate(ranked, start=1):
        p_value = _decimal(
            item["p_value"], "ASSOCIATION_RESULT_P_VALUE_INVALID"
        )
        multiplier = Decimal(family_size - rank + 1)
        running = max(running, min(Decimal(1), p_value * multiplier))
        adjusted[item["candidate_id"]] = running
        with localcontext() as context:
            context.prec = 50
            threshold = FWER_ALPHA / multiplier
        if rejection_open and p_value <= threshold:
            rejected.add(item["candidate_id"])
        else:
            rejection_open = False
    return adjusted, rejected


def apply_by_fdr_holm_family_v2(
    *,
    preregistration: Mapping[str, Any],
    family_id: str,
    candidate_results: Sequence[Mapping[str, Any]],
    evaluated_at: str,
) -> dict[str, Any]:
    """Apply frozen BY-FDR and Holm-FWER to one complete fixed family.

    Every candidate must be present exactly once.  An explicit UNKNOWN keeps
    the entire family UNKNOWN and blocks discovery claims; it is never silently
    removed to shrink the denominator.
    """

    prereg_digest = verify_v31_association_preregistration_v2(preregistration)
    family_key = _text(family_id, "ASSOCIATION_BH_FAMILY_INVALID")
    candidate_map, family = _candidate_map(preregistration, family_key)
    if isinstance(candidate_results, (str, bytes)):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_SET_INVALID"
        )
    try:
        rows = list(candidate_results)
    except TypeError as exc:
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_SET_INVALID"
        ) from exc
    if any(not isinstance(item, Mapping) for item in rows):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_RESULT_SET_INVALID"
        )
    supplied_ids = [item.get("candidate_id") for item in rows]
    if (
        len(supplied_ids) != len(set(supplied_ids))
        or set(supplied_ids) != set(candidate_map)
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_BH_COMPLETE_CANDIDATE_SET_REQUIRED"
        )
    normalized = [
        _normalize_result(item, candidate_map[item["candidate_id"]])
        for item in rows
    ]
    normalized.sort(key=lambda item: item["candidate_id"])
    all_evaluated = all(item["status"] == "EVALUATED" for item in normalized)
    if all_evaluated:
        by_adjusted, by_rejected, critical_rank, critical_p, harmonic = (
            _by_adjustments(
                normalized, family_size=family["family_size"]
            )
        )
        holm_adjusted, holm_rejected = _holm_adjustments(
            normalized, family_size=family["family_size"]
        )
        family_status = "EVALUATED_COMPLETE_FAMILY"
        multiplicity_decision_available = True
    else:
        by_adjusted = {}
        by_rejected = set()
        holm_adjusted = {}
        holm_rejected = set()
        critical_rank = None
        critical_p = None
        harmonic = _harmonic_number(family["family_size"])
        family_status = "UNKNOWN_NOT_EVALUATED_INCOMPLETE_FAMILY"
        multiplicity_decision_available = False
    result_rows = []
    for item in normalized:
        candidate_id = item["candidate_id"]
        result_rows.append(
            {
                **item,
                "by_adjusted_p_value": (
                    _decimal_text(by_adjusted[candidate_id])
                    if all_evaluated
                    else None
                ),
                "by_decision": (
                    "REJECT_NULL_AT_BY_FDR_Q_0_05"
                    if candidate_id in by_rejected
                    else (
                        "DO_NOT_REJECT_NULL_AT_BY_FDR_Q_0_05"
                        if all_evaluated
                        else "UNKNOWN_INCOMPLETE_FAMILY"
                    )
                ),
                "holm_adjusted_p_value": (
                    _decimal_text(holm_adjusted[candidate_id])
                    if all_evaluated
                    else None
                ),
                "holm_decision": (
                    "REJECT_NULL_AT_HOLM_FWER_ALPHA_0_05"
                    if candidate_id in holm_rejected
                    else (
                        "DO_NOT_REJECT_NULL_AT_HOLM_FWER_ALPHA_0_05"
                        if all_evaluated
                        else "UNKNOWN_INCOMPLETE_FAMILY"
                    )
                ),
            }
        )
    receipt = {
        "schema_id": MULTIPLICITY_RECEIPT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_scope_id": preregistration["run_scope_id"],
        "instrument_id": preregistration["instrument_id"],
        "association_preregistration_digest": prereg_digest,
        "family_id": family_key,
        "family_size": family["family_size"],
        "fdr_procedure": family["fdr_procedure"],
        "q": family["q"],
        "harmonic_constant": _decimal_text(harmonic),
        "dependency_assumption": family["dependency_assumption"],
        "ordinary_bh_enabled": False,
        "confirmatory_fwer_procedure": family[
            "confirmatory_fwer_procedure"
        ],
        "confirmatory_fwer_alpha": family["confirmatory_fwer_alpha"],
        "evaluated_at": _time_text(
            _timestamp(evaluated_at, "ASSOCIATION_BH_TIME_INVALID")
        ),
        "family_status": family_status,
        "multiplicity_decision_available": multiplicity_decision_available,
        "market_discovery_claim_allowed": False,
        "market_discovery_claim_requirement": (
            "SEPARATE_TRUSTED_ESTIMATOR_SOURCE_AND_EXTERNAL_VALIDITY_REVIEW"
        ),
        "critical_rank": critical_rank,
        "critical_p_value": (
            None if critical_p is None else _decimal_text(critical_p)
        ),
        "candidate_results": result_rows,
        "by_discovery_candidate_ids": sorted(by_rejected),
        "holm_confirmed_candidate_ids": sorted(holm_rejected),
        "interpretation_boundary": (
            "ASSOCIATION_ONLY_NOT_CAUSAL_NOT_FORECAST_PROBABILITY"
        ),
        "action_input": False,
        "probability_cloud_input": False,
        "ev_allowed": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(receipt, "multiplicity_family_receipt_digest")


def verify_by_fdr_holm_family_receipt_v2(
    receipt: Mapping[str, Any], preregistration: Mapping[str, Any]
) -> str:
    if not isinstance(receipt, Mapping):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_BH_RECEIPT_INVALID"
        )
    try:
        supplied = verify_self_digest(
            receipt, "multiplicity_family_receipt_digest"
        )
        source_rows = [
            {key: row[key] for key in _RESULT_FIELDS}
            for row in receipt["candidate_results"]
        ]
        rebuilt = apply_by_fdr_holm_family_v2(
            preregistration=preregistration,
            family_id=receipt["family_id"],
            candidate_results=source_rows,
            evaluated_at=receipt["evaluated_at"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V31AssociationPreregistrationError):
            raise
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_BH_RECEIPT_INVALID"
        ) from exc
    if (
        dict(receipt) != rebuilt
        or supplied != rebuilt["multiplicity_family_receipt_digest"]
    ):
        raise V31AssociationPreregistrationError(
            "ASSOCIATION_BH_RECEIPT_RECONSTRUCTION_MISMATCH"
        )
    return supplied


__all__ = [
    "CURRENT_EXPERIMENT_CYCLE_CAP",
    "FDR_Q",
    "FWER_ALPHA",
    "INSTRUMENT_ID",
    "MULTIPLICITY_RECEIPT_SCHEMA_ID",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "V31AssociationPreregistrationError",
    "V31_SENTIMENT_AXES",
    "apply_by_fdr_holm_family_v2",
    "build_v31_association_preregistration_v2",
    "verify_by_fdr_holm_family_receipt_v2",
    "verify_v31_association_preregistration_v2",
]
