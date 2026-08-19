"""Experimental theory-practice layer for the public-data paper runtime.

The functions in this module are deterministic transformations and validators.
They do not fetch data, identify real market participants, estimate calibrated
probabilities, or authorize a real order.  Missing observations remain typed
``UNKNOWN`` values throughout the analysis chain.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .common import TheoryPaperError, digest_json, iso_utc, parse_utc


UNKNOWN = "UNKNOWN"
EXPERIMENTAL = "EXPERIMENTAL"
PAPER_ONLY = "PAPER_ONLY"
EXPERIMENT_SYMBOLS = frozenset(
    {"SNDKUSDT", "MUUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"}
)
GLOBAL_OFFICIAL_DOMAINS = frozenset(
    {
        "federalreserve.gov",
        "sec.gov",
        "cftc.gov",
        "binance.com",
    }
)
SYMBOL_OFFICIAL_DOMAINS = {
    "SNDKUSDT": frozenset({"investor.sandisk.com"}),
    "MUUSDT": frozenset({"investors.micron.com"}),
    "BTCUSDT": frozenset({"bitcoin.org"}),
    "ETHUSDT": frozenset({"ethereum.org", "blog.ethereum.org"}),
    "SOLUSDT": frozenset({"solana.com"}),
    "HYPEUSDT": frozenset(
        {
            "hyperliquid.gitbook.io",
            "t.me",
        }
    ),
}

TIMEFRAME_ROLES = (
    ("1w", "BACKGROUND_RISK"),
    ("1d", "STRUCTURAL_CONTEXT"),
    ("4h", "OPERATIONAL_REGIME"),
    ("1h", "SETUP"),
    ("15m", "EVALUATION_TRIGGER"),
)

PHI_IDS = (
    "PHI_UPWARD_CONTINUATION",
    "PHI_DOWNWARD_CONTINUATION",
    "PHI_ABSORPTION_REVERSAL",
    "PHI_BREAKOUT",
    "PHI_RANGE",
    "PHI_OTHER_UNKNOWN",
)

OBSERVABLE_IDS = (
    "REFERENCE_PRICE",
    "D_SIGNED_TAKER_IMBALANCE",
    "D_HOURLY_TAKER_BUY_SELL_RATIO",
    "L_OI_VALUE_1H_CHANGE_PCT",
    "C_FUNDING_RATE",
    "15M_DIRECTION",
    "1H_DIRECTION",
    "4H_DIRECTION",
    "1D_DIRECTION",
    "OPERATIONAL_PHASE",
    "LOCATION_STAGE",
)
PREDICATE_OPERATORS = ("EQ", "NE", "GT", "GTE", "LT", "LTE")

ALLOWED_ACTIONS = (
    "OPEN_LONG",
    "OPEN_SHORT",
    "ADD_LONG",
    "ADD_SHORT",
    "REDUCE",
    "EXIT",
    "MODIFY_ORDERS",
    "CANCEL_ORDER",
    "KEEP",
    "ABSTAIN",
)
NEW_RISK_ACTIONS = frozenset({"OPEN_LONG", "OPEN_SHORT", "ADD_LONG", "ADD_SHORT"})
INACTIVE_ACTIONS = frozenset({"KEEP", "ABSTAIN"})
PORTFOLIO_ACTIONS = (
    "UPDATE_PROTECTION",
    "KEEP_ORDER",
    "REPLACE_ORDER",
    "CANCEL_ORDER",
    "PLACE_LIMIT",
    "MARKET",
    "CLOSE",
    "HOLD",
)
PORTFOLIO_NEW_RISK_ACTIONS = frozenset({"KEEP_ORDER", "REPLACE_ORDER", "PLACE_LIMIT", "MARKET"})
MARKET_ACTIONABILITY_VALUES = frozenset(
    {"ACTIONABLE", "DATA_INVALID", "RISK_VETO", "NOT_ACTIONABLE"}
)
EXECUTION_INTENT_VALUES = frozenset({"EXECUTE_NOW", "PLAN_ONLY", "NO_NEW_RISK"})

_FORBIDDEN_DECISION_KEY_PREFIXES = (
    "apikey",
    "apisecret",
    "secret",
    "credential",
    "accountid",
    "privatekey",
    "liveorder",
    "livetrading",
    "realorder",
    "accesstoken",
    "refreshtoken",
    "signature",
    "listenkey",
    "passphrase",
    "mnemonic",
    "seedphrase",
)
_SECRET_VALUE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?<![A-Za-z0-9])sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{12,}",
        r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])(?:ghp_|github_pat_|glpat-|xox[baprs]-)[A-Za-z0-9_-]{12,}",
        r"(?<![A-Za-z0-9])AIza[A-Za-z0-9_-]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"(?<![A-Za-z0-9])Bearer\s+[A-Za-z0-9._~+/-]{12,}",
        r"(?:api[_ -]?key|api[_ -]?secret|access[_ -]?token|private[_ -]?key)"
        r"\s*[:=]\s*[^\s,;]{8,}",
    )
)

ISSUE_TAXONOMY: dict[str, dict[str, str]] = {
    "DATA_QUALITY": {
        "change_axis": "MEASUREMENT",
        "proposal": "Add or repair one point-in-time source or explicitly narrow the claim.",
        "test": "The next frozen window has fewer required UNKNOWN fields without look-ahead.",
    },
    "STATE_CLASSIFICATION": {
        "change_axis": "MULTISCALE_STATE",
        "proposal": "Revise one state predicate while preserving timeframe role direction.",
        "test": "The revised predicate resolves the cited state error on a new unseen window.",
    },
    "PHI_COMPETITION": {
        "change_axis": "PHI_COMPETITION",
        "proposal": "Revise one predeclared support, contradiction, or OTHER routing rule.",
        "test": "Competing explanations remain visible and the cited forced story no longer occurs.",
    },
    "FALSIFICATION": {
        "change_axis": "HYPOTHESIS_LIFECYCLE",
        "proposal": "Make the hard falsifier or expiry objectively observable before action.",
        "test": "The next hypothesis can be terminally resolved without rewriting its thesis.",
    },
    "ACTION_GEOMETRY": {
        "change_axis": "ACTION_GEOMETRY",
        "proposal": "Revise one entry, invalidation, target, or reward-risk construction rule.",
        "test": "A new unseen candidate is directionally valid and meets the frozen reward-risk floor.",
    },
    "RISK_DISCIPLINE": {
        "change_axis": "RISK",
        "proposal": "Tighten the separate position-risk gate; do not increase size from conviction.",
        "test": "Every new-risk action in the next window has bounded loss and a valid stop.",
    },
    "EXECUTION": {
        "change_axis": "EXECUTION",
        "proposal": "Revise one fill, spread, slippage, or order-lifecycle assumption.",
        "test": "The next review can reconcile every intended action to an immutable paper receipt.",
    },
    "UNDERTRADING": {
        "change_axis": "ACTIVE_PROBE",
        "proposal": "Require a bounded paper probe when data are actionable and inactivity persists.",
        "test": "The next eligible window contains an executed probe or a typed safety veto.",
    },
    "OVERTRADING": {
        "change_axis": "ACTION_FREQUENCY",
        "proposal": "Require a new observation-frame delta before adding or reversing risk.",
        "test": "Repeated actions no longer occur without a new evidence or lifecycle event.",
    },
    "POSTHOC_REASONING": {
        "change_axis": "REVIEW_DISCIPLINE",
        "proposal": "Freeze thesis, falsifier, expiry, and evidence references before paper execution.",
        "test": "The next review evaluates the frozen thesis without retrospective rewriting.",
    },
    "NEWS_CAUSAL_OVERREACH": {
        "change_axis": "EVENT_EVIDENCE",
        "proposal": "Treat headline metadata as context until timing and response evidence are linked.",
        "test": "No directional claim is attributed to a headline alone in the next window.",
    },
    "ACTOR_IDENTITY_OVERREACH": {
        "change_axis": "ACTOR_INFERENCE",
        "proposal": "Replace identity stories with observable behavior-class hypotheses.",
        "test": "All actor claims in the next window remain non-identifying and falsifiable.",
    },
}


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _known(value: Any) -> bool:
    return value is not None and value != UNKNOWN


def _value(value: Any) -> Any:
    if value is None:
        return UNKNOWN
    if isinstance(value, float) and not math.isfinite(value):
        return UNKNOWN
    return copy.deepcopy(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _axis(axis_id: str, observations: Mapping[str, Any], boundary: str) -> dict[str, Any]:
    normalized = {key: _value(value) for key, value in observations.items()}
    known_count = sum(_known(value) for value in normalized.values())
    if known_count == 0:
        status = UNKNOWN
    elif known_count == len(normalized):
        status = "OBSERVED"
    else:
        status = "PARTIAL"
    return {
        "axis_id": axis_id,
        "status": status,
        "observations": normalized,
        "missing_fields": sorted(key for key, value in normalized.items() if not _known(value)),
        "interpretation_boundary": boundary,
    }


def _measurement_snapshot(symbol_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(symbol_snapshot.get("symbol", "")).strip()
    if not symbol:
        raise TheoryPaperError("symbol snapshot has no symbol")
    measures = _mapping(symbol_snapshot.get("measures"))
    directional = _mapping(measures.get("directional_pressure_D"))
    recent = _mapping(directional.get("recent_trades"))
    leverage = _mapping(measures.get("leverage_L"))
    crowding = _mapping(measures.get("crowding_C"))
    forced = _mapping(measures.get("forced_deleveraging_F"))
    liquidity = _mapping(measures.get("liquidity_resilience_R"))
    raw_timeframes = _mapping(measures.get("timeframes"))

    timeframes: dict[str, Any] = {}
    technical_fields = (
        "price",
        "change_1_bar_pct",
        "change_6_bar_pct",
        "ema20",
        "ema50",
        "ema200",
        "rsi14",
        "atr14",
        "atr_pct",
        "adx14",
        "efficiency_ratio10",
        "macd_histogram",
        "bollinger_middle",
        "bollinger_upper",
        "bollinger_lower",
        "bollinger_bandwidth",
        "bollinger_percent_b",
        "relative_volume20",
        "trend_state",
        "supports",
        "resistances",
    )
    for timeframe, role in TIMEFRAME_ROLES:
        source = _mapping(raw_timeframes.get(timeframe))
        source_observations = {
            field: source.get(field) if source.get("status") != UNKNOWN else None
            for field in technical_fields
        }
        state = _axis(
            f"K_{timeframe}",
            source_observations,
            "CLOSED_BAR_TECHNICAL_MEASURES_NOT_A_SIGNAL",
        )
        state["role"] = role
        state["source_status"] = _value(source.get("status"))
        timeframes[timeframe] = state

    forced_status = forced.get("status")
    f_notional = forced.get("notional") if forced_status != UNKNOWN else None
    f_count = forced.get("event_count") if forced_status != UNKNOWN else None
    axes = {
        "D": _axis(
            "D_DIRECTIONAL_PRESSURE",
            {
                "signed_taker_imbalance": recent.get("signed_taker_imbalance"),
                "recent_window_vwap": recent.get("vwap"),
                "hourly_taker_buy_sell_ratio": directional.get(
                    "hourly_taker_buy_sell_ratio"
                ),
                "recent_window_status": recent.get("status"),
            },
            "FLOW_PRESSURE_PROXY_NOT_PARTICIPANT_IDENTITY",
        ),
        "L": _axis(
            "L_LEVERAGE",
            {
                "open_interest_contracts": leverage.get("open_interest_contracts"),
                "open_interest_value_1h_change_pct": leverage.get(
                    "open_interest_value_1h_change_pct"
                ),
            },
            "OI_CHANGE_HAS_NO_DIRECTIONAL_TRUTH_ALONE",
        ),
        "C": _axis(
            "C_CROWDING",
            {
                "funding_rate": crowding.get("funding_rate"),
                "basis_bps": crowding.get("basis_bps"),
                "global_account_long_short_ratio": crowding.get(
                    "global_account_long_short_ratio"
                ),
                "top_position_long_short_ratio": crowding.get(
                    "top_position_long_short_ratio"
                ),
            },
            "MULTI_PROXY_VECTOR_NOT_SINGLE_EMOTION_SCORE",
        ),
        "F": _axis(
            "F_FORCED_DELEVERAGING",
            {
                "window_status": forced_status,
                "event_count_lower_bound": f_count,
                "notional_lower_bound": f_notional,
            },
            "API_WINDOW_IS_A_LOWER_BOUND_AND_MISSING_NEVER_MEANS_ZERO",
        ),
        "R": _axis(
            "R_LIQUIDITY_RESILIENCE",
            {
                "snapshot_status": liquidity.get("status"),
                "spread_bps": liquidity.get("spread_bps"),
                "top20_imbalance": liquidity.get("top20_imbalance"),
                "buy_1000_impact_bps": liquidity.get("buy_1000_impact_bps"),
                "sell_1000_impact_bps": liquidity.get("sell_1000_impact_bps"),
                "strict_resilience_available": (
                    True if liquidity.get("strict_resilience_available") is True else None
                ),
            },
            "ONE_BOOK_SNAPSHOT_CANNOT_PROVE_ABSORPTION_OR_REPLENISHMENT",
        ),
        "K": {
            "axis_id": "K_CLOSED_BAR_TECHNICAL",
            "status": (
                UNKNOWN
                if all(item["status"] == UNKNOWN for item in timeframes.values())
                else "PARTIAL"
                if any(item["status"] == UNKNOWN for item in timeframes.values())
                else "OBSERVED"
            ),
            "timeframes": timeframes,
            "interpretation_boundary": "TIMEFRAMES_HAVE_ORDERED_ROLES_AND_DO_NOT_VOTE",
        },
    }
    quality = _mapping(symbol_snapshot.get("data_quality"))
    result: dict[str, Any] = {
        "schema_version": "MeasurementSnapshot.v1-experimental",
        "symbol": symbol,
        "venue": _value(symbol_snapshot.get("venue")),
        "observed_at": _value(symbol_snapshot.get("observed_at")),
        "reference_price": _value(measures.get("price")),
        "axes": axes,
        "data_quality": {
            "coverage_ratio": _value(quality.get("coverage_ratio")),
            "error_count": _value(quality.get("error_count")),
            "errors": _value(quality.get("errors")),
            "strict_resilience_available": (
                True if quality.get("strict_R_available") is True else False
            ),
            "liquidation_zero_certainty": (
                True if quality.get("liquidation_zero_certainty") is True else False
            ),
        },
        "source_raw_digest": _value(symbol_snapshot.get("raw_digest")),
        "epistemic_status": EXPERIMENTAL,
    }
    result["measurement_snapshot_id"] = "MS-" + digest_json(result)[:20]
    return result


def _technical(measurement: Mapping[str, Any], timeframe: str) -> Mapping[str, Any]:
    axes = _mapping(measurement.get("axes"))
    k_axis = _mapping(axes.get("K"))
    frames = _mapping(k_axis.get("timeframes"))
    frame = _mapping(frames.get(timeframe))
    return _mapping(frame.get("observations"))


def _classify_momentum(frame: Mapping[str, Any]) -> str:
    rsi = _finite(frame.get("rsi14"))
    histogram = _finite(frame.get("macd_histogram"))
    if rsi is None or histogram is None:
        return UNKNOWN
    if rsi >= 55.0 and histogram > 0:
        return "BULLISH"
    if rsi <= 45.0 and histogram < 0:
        return "BEARISH"
    return "MIXED"


def _classify_volatility(frame: Mapping[str, Any]) -> str:
    atr_pct = _finite(frame.get("atr_pct"))
    if atr_pct is None:
        return UNKNOWN
    if atr_pct < 0.5:
        return "LOW"
    if atr_pct <= 1.5:
        return "MEDIUM"
    return "HIGH"


def _classify_participation(frame: Mapping[str, Any]) -> str:
    rvol = _finite(frame.get("relative_volume20"))
    if rvol is None:
        return UNKNOWN
    if rvol < 0.75:
        return "LOW"
    if rvol > 1.5:
        return "HIGH"
    return "NORMAL"


def _multi_scale_state(measurement: Mapping[str, Any]) -> dict[str, Any]:
    role_states: list[dict[str, Any]] = []
    for timeframe, role in TIMEFRAME_ROLES:
        frame = _technical(measurement, timeframe)
        trend = frame.get("trend_state")
        direction = (
            trend if trend in {"UP", "DOWN", "RANGE", "TRANSITION"} else UNKNOWN
        )
        role_states.append(
            {
                "timeframe": timeframe,
                "role": role,
                "direction_state": direction,
                "momentum_state": _classify_momentum(frame),
                "volatility_state": _classify_volatility(frame),
                "participation_state": _classify_participation(frame),
                "state_status": UNKNOWN if direction == UNKNOWN else "OBSERVED_DERIVED",
            }
        )

    by_timeframe = {item["timeframe"]: item for item in role_states}
    parent = by_timeframe["1d"]["direction_state"]
    operational = by_timeframe["4h"]["direction_state"]
    if UNKNOWN in {parent, operational}:
        alignment = UNKNOWN
    elif parent == operational and parent in {"UP", "DOWN", "RANGE"}:
        alignment = "ALIGNED"
    elif {parent, operational} == {"UP", "DOWN"}:
        alignment = "CONFLICT"
    else:
        alignment = "TRANSITION"
    result: dict[str, Any] = {
        "schema_version": "MultiScaleStateBelief.v1-experimental",
        "symbol": measurement["symbol"],
        "ordered_role_profile": "EXPERIMENTAL_CROSS_ASSET_1W_1D_4H_1H_15M_V1",
        "role_states": role_states,
        "parent_operational_alignment": alignment,
        "operational_bias": operational,
        "setup_bias": by_timeframe["1h"]["direction_state"],
        "trigger_bias": by_timeframe["15m"]["direction_state"],
        "aggregation_rule": "NO_TIMEFRAME_VOTING_LOWER_ROLE_CANNOT_OVERRIDE_PARENT_ROLE",
        "epistemic_status": EXPERIMENTAL,
    }
    result["multi_scale_state_belief_id"] = "MSS-" + digest_json(result)[:20]
    return result


def _numeric_levels(value: Any, *, below: float | None = None, above: float | None = None) -> list[float]:
    if not isinstance(value, list):
        return []
    output = sorted({_finite(item) for item in value if _finite(item) is not None})
    numbers = [number for number in output if number is not None]
    if below is not None:
        numbers = [number for number in numbers if number < below]
    if above is not None:
        numbers = [number for number in numbers if number > above]
    return numbers


def _structural_position(
    measurement: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    price = _finite(measurement.get("reference_price"))
    frame = _technical(measurement, "4h")
    atr_value = _finite(frame.get("atr14"))
    supports = _numeric_levels(frame.get("supports"), below=price) if price else []
    resistances = _numeric_levels(frame.get("resistances"), above=price) if price else []
    support = max(supports) if supports else None
    resistance = min(resistances) if resistances else None

    location: str = UNKNOWN
    normalized_location: float | str = UNKNOWN
    if (
        price is not None
        and support is not None
        and resistance is not None
        and resistance > support
    ):
        fraction = (price - support) / (resistance - support)
        normalized_location = round(fraction, 6)
        location = (
            "LOWER_THIRD"
            if fraction <= 1.0 / 3.0
            else "UPPER_THIRD"
            if fraction >= 2.0 / 3.0
            else "MIDDLE_THIRD"
        )

    stage = UNKNOWN
    if price is not None and atr_value is not None and atr_value > 0:
        near = 0.35 * atr_value
        near_support = support is not None and abs(price - support) <= near
        near_resistance = resistance is not None and abs(resistance - price) <= near
        if near_support and near_resistance:
            stage = "COMPRESSION_BETWEEN_LEVELS"
        elif near_support:
            stage = "NEAR_REGISTERED_SUPPORT"
        elif near_resistance:
            stage = "NEAR_REGISTERED_RESISTANCE"
        elif support is not None and resistance is not None:
            stage = "BETWEEN_REGISTERED_LEVELS"

    bollinger_upper = _finite(frame.get("bollinger_upper"))
    bollinger_lower = _finite(frame.get("bollinger_lower"))
    rvol = _finite(frame.get("relative_volume20"))
    expansion = UNKNOWN
    if price is not None and rvol is not None:
        if bollinger_upper is not None and price > bollinger_upper and rvol > 1.2:
            expansion = "UPSIDE_EXPANSION_PROXY"
        elif bollinger_lower is not None and price < bollinger_lower and rvol > 1.2:
            expansion = "DOWNSIDE_EXPANSION_PROXY"
        elif bollinger_lower is not None and bollinger_upper is not None:
            expansion = "INSIDE_BAND"

    result: dict[str, Any] = {
        "schema_version": "StructuralPosition.v1-experimental",
        "symbol": measurement["symbol"],
        "reference_timeframe": "4h",
        "reference_price": _value(price),
        "operational_phase": _value(state.get("operational_bias")),
        "nearest_registered_support": _value(support),
        "nearest_registered_resistance": _value(resistance),
        "normalized_range_location": normalized_location,
        "range_location": location,
        "location_stage": stage,
        "expansion_state": expansion,
        "boundary": "REGISTERED_PIVOTS_AND_BANDS_ARE_CANDIDATE_GEOMETRY_NOT_SIGNAL",
        "epistemic_status": EXPERIMENTAL,
    }
    result["structural_position_id"] = "SP-" + digest_json(result)[:20]
    return result


def _signal(
    destination: dict[str, dict[str, list[str]]],
    phi_id: str,
    direction: str,
    reason: str,
) -> None:
    destination[phi_id][direction].append(reason)


def _ordinal(for_count: int, against_count: int, *, capped: bool = False) -> str:
    if for_count == 0 and against_count == 0:
        return UNKNOWN
    if for_count and against_count:
        return "MIXED"
    if for_count == 0:
        return "CONTRADICTED"
    if capped:
        return "WEAK"
    if for_count >= 3:
        return "STRONG"
    if for_count == 2:
        return "MODERATE"
    return "WEAK"


def _phi_competition(
    measurement: Mapping[str, Any],
    state: Mapping[str, Any],
    structural: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = {
        phi_id: {"for": [], "against": [], "unresolved": []} for phi_id in PHI_IDS
    }
    operational = state.get("operational_bias")
    setup = state.get("setup_bias")
    trigger = state.get("trigger_bias")
    if operational == "UP":
        _signal(evidence, "PHI_UPWARD_CONTINUATION", "for", "4H_OPERATIONAL_UP")
        _signal(evidence, "PHI_DOWNWARD_CONTINUATION", "against", "4H_OPERATIONAL_UP")
    elif operational == "DOWN":
        _signal(evidence, "PHI_DOWNWARD_CONTINUATION", "for", "4H_OPERATIONAL_DOWN")
        _signal(evidence, "PHI_UPWARD_CONTINUATION", "against", "4H_OPERATIONAL_DOWN")
    elif operational == "RANGE":
        _signal(evidence, "PHI_RANGE", "for", "4H_OPERATIONAL_RANGE")
        _signal(evidence, "PHI_UPWARD_CONTINUATION", "against", "4H_OPERATIONAL_RANGE")
        _signal(evidence, "PHI_DOWNWARD_CONTINUATION", "against", "4H_OPERATIONAL_RANGE")
    else:
        evidence["PHI_OTHER_UNKNOWN"]["for"].append("4H_OPERATIONAL_STATE_UNKNOWN_OR_TRANSITION")

    if setup == "UP":
        _signal(evidence, "PHI_UPWARD_CONTINUATION", "for", "1H_SETUP_UP")
    elif setup == "DOWN":
        _signal(evidence, "PHI_DOWNWARD_CONTINUATION", "for", "1H_SETUP_DOWN")
    elif setup == "RANGE":
        _signal(evidence, "PHI_RANGE", "for", "1H_SETUP_RANGE")
    if trigger in {"UP", "DOWN"} and operational in {"UP", "DOWN"} and trigger != operational:
        evidence["PHI_ABSORPTION_REVERSAL"]["for"].append(
            "15M_TRIGGER_OPPOSES_4H_OPERATIONAL_DIRECTION"
        )

    axes = _mapping(measurement.get("axes"))
    d_obs = _mapping(_mapping(axes.get("D")).get("observations"))
    imbalance = _finite(d_obs.get("signed_taker_imbalance"))
    if imbalance is not None:
        if imbalance > 0.08:
            _signal(evidence, "PHI_UPWARD_CONTINUATION", "for", "RECENT_TAKER_PRESSURE_POSITIVE")
            if trigger not in {"UP", UNKNOWN}:
                evidence["PHI_ABSORPTION_REVERSAL"]["for"].append(
                    "BUY_PRESSURE_WITHOUT_UP_TRIGGER_RESPONSE"
                )
        elif imbalance < -0.08:
            _signal(evidence, "PHI_DOWNWARD_CONTINUATION", "for", "RECENT_TAKER_PRESSURE_NEGATIVE")
            if trigger not in {"DOWN", UNKNOWN}:
                evidence["PHI_ABSORPTION_REVERSAL"]["for"].append(
                    "SELL_PRESSURE_WITHOUT_DOWN_TRIGGER_RESPONSE"
                )

    expansion = structural.get("expansion_state")
    if expansion == "UPSIDE_EXPANSION_PROXY":
        evidence["PHI_BREAKOUT"]["for"].append("4H_UPSIDE_BAND_EXPANSION_WITH_RVOL")
        evidence["PHI_RANGE"]["against"].append("4H_UPSIDE_BAND_EXPANSION_WITH_RVOL")
    elif expansion == "DOWNSIDE_EXPANSION_PROXY":
        evidence["PHI_BREAKOUT"]["for"].append("4H_DOWNSIDE_BAND_EXPANSION_WITH_RVOL")
        evidence["PHI_RANGE"]["against"].append("4H_DOWNSIDE_BAND_EXPANSION_WITH_RVOL")
    elif expansion == "INSIDE_BAND" and operational == "RANGE":
        evidence["PHI_RANGE"]["for"].append("4H_INSIDE_BAND_RANGE")

    quality = _mapping(measurement.get("data_quality"))
    coverage = _finite(quality.get("coverage_ratio"))
    if coverage is None or coverage < 0.8:
        evidence["PHI_OTHER_UNKNOWN"]["for"].append("REQUIRED_DATA_COVERAGE_INCOMPLETE")
    if _mapping(axes.get("R")).get("status") == UNKNOWN:
        evidence["PHI_ABSORPTION_REVERSAL"]["unresolved"].append(
            "STRICT_RESILIENCE_UNAVAILABLE"
        )
    else:
        evidence["PHI_ABSORPTION_REVERSAL"]["unresolved"].append(
            "ONE_SNAPSHOT_CANNOT_ESTABLISH_TEMPORAL_ABSORPTION"
        )

    common_specs = {
        "PHI_UPWARD_CONTINUATION": {
            "label": "上涨延续",
            "direction": "UP",
            "next": ["SAME_DIRECTION_STRUCTURE_HOLDS", "PRESSURE_REMAINS_POSITIVE"],
            "soft": ["MOMENTUM_DECAYS", "PRESSURE_FLIPS_BRIEFLY"],
            "hard": ["4H_DOWN_STRUCTURE_CONFIRMED_AFTER_DECISION"],
        },
        "PHI_DOWNWARD_CONTINUATION": {
            "label": "下跌延续",
            "direction": "DOWN",
            "next": ["SAME_DIRECTION_STRUCTURE_HOLDS", "PRESSURE_REMAINS_NEGATIVE"],
            "soft": ["MOMENTUM_DECAYS", "PRESSURE_FLIPS_BRIEFLY"],
            "hard": ["4H_UP_STRUCTURE_CONFIRMED_AFTER_DECISION"],
        },
        "PHI_ABSORPTION_REVERSAL": {
            "label": "吸收反转",
            "direction": UNKNOWN,
            "next": ["PRESSURE_PERSISTS_WHILE_MARGINAL_PRICE_IMPACT_FALLS", "REVERSE_STRUCTURE_CONFIRMS"],
            "soft": ["SINGLE_WICK_WITHOUT_FOLLOW_THROUGH"],
            "hard": ["PRESSURE_REGAINS_SAME_DIRECTION_EXPANSION"],
        },
        "PHI_BREAKOUT": {
            "label": "突破",
            "direction": (
                "UP"
                if expansion == "UPSIDE_EXPANSION_PROXY"
                else "DOWN"
                if expansion == "DOWNSIDE_EXPANSION_PROXY"
                else UNKNOWN
            ),
            "next": ["BREAKOUT_LEVEL_HOLDS_ON_CLOSED_BAR", "PARTICIPATION_REMAINS_ELEVATED"],
            "soft": ["PRICE_RETURNS_INSIDE_PRIOR_BAND"],
            "hard": ["BREAKOUT_LEVEL_FAILS_AND_OPPOSITE_STRUCTURE_CONFIRMS"],
        },
        "PHI_RANGE": {
            "label": "区间",
            "direction": "NEUTRAL",
            "next": ["BOTH_REGISTERED_BOUNDARIES_REMAIN_VALID", "CENTER_REVERSION_REPEATS"],
            "soft": ["ONE_SIDE_PRESSURE_INCREASES"],
            "hard": ["CLOSED_BAR_BREAKOUT_HOLDS_BEYOND_CONFIRMATION_WINDOW"],
        },
        "PHI_OTHER_UNKNOWN": {
            "label": "其他或未知",
            "direction": UNKNOWN,
            "next": ["NEW_INDEPENDENT_OBSERVATION_DISTINGUISHES_REGISTERED_PATHS"],
            "soft": ["ONE_REGISTERED_PHI_GAINS_INDEPENDENT_SUPPORT"],
            "hard": ["REGISTERED_LIBRARY_COVERS_NEW_OBSERVATIONS_WITHOUT_DATA_CONFLICT"],
        },
    }
    hypotheses: list[dict[str, Any]] = []
    for phi_id in PHI_IDS:
        item = evidence[phi_id]
        cap = phi_id == "PHI_ABSORPTION_REVERSAL"
        spec = common_specs[phi_id]
        hypotheses.append(
            {
                "phi_id": phi_id,
                "label": spec["label"],
                "direction": spec["direction"],
                "support_ordinal": _ordinal(
                    len(item["for"]), len(item["against"]), capped=cap
                ),
                "evidence_for": item["for"],
                "evidence_against": item["against"],
                "unresolved": item["unresolved"],
                "next_observable_support": spec["next"],
                "soft_contradictions": spec["soft"],
                "hard_falsifiers": spec["hard"],
                "expiry_hours": 8,
                "is_probability": False,
                "probability_status": "UNAVAILABLE_NOT_CALIBRATED",
            }
        )

    result: dict[str, Any] = {
        "schema_version": "PathHypothesisCompetition.v1-experimental",
        "symbol": measurement["symbol"],
        "competition_mode": "QUALITATIVE_ORDINAL_NON_NORMALIZED",
        "finite_registry": list(PHI_IDS),
        "hypotheses": hypotheses,
        "single_top_path": "UNKNOWN_NO_CALIBRATED_COMPETITION_SET",
        "normalization_rule": "FORBIDDEN_ORDINAL_SUPPORT_IS_NOT_PROBABILITY",
        "epistemic_status": EXPERIMENTAL,
    }
    result["phi_competition_id"] = "PHIC-" + digest_json(result)[:20]
    return result


def _actor_behavior_hypotheses(measurement: Mapping[str, Any]) -> dict[str, Any]:
    axes = _mapping(measurement.get("axes"))
    items: list[dict[str, Any]] = []
    d_obs = _mapping(_mapping(axes.get("D")).get("observations"))
    imbalance = _finite(d_obs.get("signed_taker_imbalance"))
    if imbalance is not None and abs(imbalance) >= 0.08:
        side = "BUY" if imbalance > 0 else "SELL"
        items.append(
            {
                "behavior_hypothesis_id": f"BH-AGGRESSIVE-{side}",
                "behavior_class": f"OBSERVED_AGGRESSIVE_{side}_INITIATION_PROXY",
                "inference": f"Recent sampled taker flow is {side.lower()}-skewed.",
                "evidence_refs": ["D.signed_taker_imbalance"],
                "alternative_explanations": ["HEDGING", "ARBITRAGE", "SHORT_WINDOW_SAMPLING"],
                "identity_status": "NOT_IDENTIFIED",
            }
        )
    c_obs = _mapping(_mapping(axes.get("C")).get("observations"))
    funding = _finite(c_obs.get("funding_rate"))
    global_ratio = _finite(c_obs.get("global_account_long_short_ratio"))
    if funding is not None or global_ratio is not None:
        if (funding is not None and funding > 0) or (
            global_ratio is not None and global_ratio > 1.1
        ):
            side = "LONG"
        elif (funding is not None and funding < 0) or (
            global_ratio is not None and global_ratio < 0.9
        ):
            side = "SHORT"
        else:
            side = "BALANCED_OR_MIXED"
        items.append(
            {
                "behavior_hypothesis_id": f"BH-CROWDING-{side}",
                "behavior_class": f"{side}_POSITIONING_PROXY",
                "inference": "Funding and account-ratio proxies suggest a crowding state, not intent.",
                "evidence_refs": ["C.funding_rate", "C.global_account_long_short_ratio"],
                "alternative_explanations": ["BASIS_TRADES", "VENUE_LOCAL_COMPOSITION", "HEDGING"],
                "identity_status": "NOT_IDENTIFIED",
            }
        )
    l_obs = _mapping(_mapping(axes.get("L")).get("observations"))
    oi_change = _finite(l_obs.get("open_interest_value_1h_change_pct"))
    if oi_change is not None and abs(oi_change) >= 0.5:
        items.append(
            {
                "behavior_hypothesis_id": "BH-LEVERAGE-BUILD" if oi_change > 0 else "BH-LEVERAGE-REDUCE",
                "behavior_class": "LEVERAGE_BUILDUP_PROXY" if oi_change > 0 else "LEVERAGE_REDUCTION_PROXY",
                "inference": "Open-interest value changed materially; trade direction and owner are unknown.",
                "evidence_refs": ["L.open_interest_value_1h_change_pct"],
                "alternative_explanations": ["PRICE_DENOMINATOR_CHANGE", "HEDGING", "ROLL_OR_CLOSE"],
                "identity_status": "NOT_IDENTIFIED",
            }
        )
    result: dict[str, Any] = {
        "schema_version": "ActorBehaviorHypotheses.v1-experimental",
        "symbol": measurement["symbol"],
        "status": "INFERRED" if items else UNKNOWN,
        "items": items,
        "epistemic_boundary": (
            "BEHAVIOR_CLASS_INFERENCE_ONLY; NO PERSON, INSTITUTION, WHALE, "
            "MARKET_MAKER, OR ACCOUNT IDENTITY IS OBSERVED"
        ),
        "epistemic_status": EXPERIMENTAL,
    }
    result["actor_behavior_hypotheses_id"] = "ABH-" + digest_json(result)[:20]
    return result


def _candidate(
    symbol: str,
    setup_type: str,
    side: str,
    entry_low: float | None,
    entry_high: float | None,
    stop: float | None,
    target: float | None,
    *,
    source: str,
    minimum_rr: float,
) -> dict[str, Any]:
    numbers = (entry_low, entry_high, stop, target)
    ready = all(value is not None and math.isfinite(value) for value in numbers)
    rr: float | None = None
    if ready:
        midpoint = (entry_low + entry_high) / 2.0  # type: ignore[operator]
        risk = midpoint - stop if side == "LONG" else stop - midpoint  # type: ignore[operator]
        reward = target - midpoint if side == "LONG" else midpoint - target  # type: ignore[operator]
        oriented = risk > 0 and reward > 0
        rr = reward / risk if oriented else None
        ready = oriented and rr >= minimum_rr
    candidate: dict[str, Any] = {
        "symbol": symbol,
        "setup_type": setup_type,
        "side": side,
        "entry_zone": {
            "low": _value(entry_low),
            "high": _value(entry_high),
        },
        "stop_loss": _value(stop),
        "take_profit": _value(target),
        "reward_risk_at_entry_mid": _value(None if rr is None else round(rr, 4)),
        "minimum_reward_risk": minimum_rr,
        "geometry_source": source,
        "status": "RESEARCH_READY" if ready else "REJECTED_OR_UNKNOWN_GEOMETRY",
        "max_notional_usdt": UNKNOWN,
        "permission": "REQUIRES_SEPARATE_PORTFOLIO_AND_RISK_GATE",
        "execution_scope": PAPER_ONLY,
        "is_order": False,
    }
    candidate["geometry_candidate_id"] = "AG-" + digest_json(candidate)[:20]
    return candidate


def _geometry_candidates(
    measurement: Mapping[str, Any], config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    symbol = str(measurement["symbol"])
    frame = _technical(measurement, "1h")
    price = _finite(measurement.get("reference_price"))
    atr_value = _finite(frame.get("atr14"))
    supports = _numeric_levels(frame.get("supports"), below=price) if price else []
    resistances = _numeric_levels(frame.get("resistances"), above=price) if price else []
    support = max(supports) if supports else None
    resistance = min(resistances) if resistances else None
    minimum_rr = _finite(config.get("minimum_reward_risk")) or 1.5
    if minimum_rr < 1.0:
        minimum_rr = 1.0

    candidates: list[dict[str, Any]] = []
    if support is not None and atr_value is not None and atr_value > 0:
        low = support
        high = support + 0.25 * atr_value
        stop = support - 0.75 * atr_value
        target = resistance
        candidates.append(
            _candidate(
                symbol,
                "SUPPORT_RETEST",
                "LONG",
                low,
                high,
                stop,
                target,
                source="1H_REGISTERED_SUPPORT_ATR_AND_RESISTANCE",
                minimum_rr=minimum_rr,
            )
        )
        candidates.append(
            _candidate(
                symbol,
                "SUPPORT_BREAKDOWN",
                "SHORT",
                support - 0.2 * atr_value,
                support,
                support + 0.75 * atr_value,
                support - 2.0 * atr_value,
                source="1H_REGISTERED_SUPPORT_AND_ATR_DERIVED_2R_TARGET",
                minimum_rr=minimum_rr,
            )
        )
    if resistance is not None and atr_value is not None and atr_value > 0:
        candidates.append(
            _candidate(
                symbol,
                "RESISTANCE_REJECTION",
                "SHORT",
                resistance - 0.25 * atr_value,
                resistance,
                resistance + 0.75 * atr_value,
                support,
                source="1H_REGISTERED_RESISTANCE_ATR_AND_SUPPORT",
                minimum_rr=minimum_rr,
            )
        )
        candidates.append(
            _candidate(
                symbol,
                "RESISTANCE_BREAKOUT",
                "LONG",
                resistance,
                resistance + 0.2 * atr_value,
                resistance - 0.75 * atr_value,
                resistance + 2.0 * atr_value,
                source="1H_REGISTERED_RESISTANCE_AND_ATR_DERIVED_2R_TARGET",
                minimum_rr=minimum_rr,
            )
        )
    if not candidates:
        candidates.append(
            _candidate(
                symbol,
                "UNKNOWN",
                "UNKNOWN",
                None,
                None,
                None,
                None,
                source="INSUFFICIENT_1H_LEVEL_OR_ATR_DATA",
                minimum_rr=minimum_rr,
            )
        )
    return candidates


def _canonical_news_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return iso_utc(parse_utc(value))
    except TheoryPaperError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            return None
        return iso_utc(parsed)


def _news_context(
    news_snapshot: Mapping[str, Any],
    symbol: str,
    decision_at: str,
) -> dict[str, Any]:
    queries = _mapping(news_snapshot.get("queries"))
    retrieved_at = _canonical_news_timestamp(news_snapshot.get("observed_at"))
    if retrieved_at is None:
        retrieved_at = decision_at
    candidates = (
        queries.get(symbol),
        queries.get(symbol.removesuffix("USDT")),
        queries.get("market"),
    )
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        source = _mapping(candidate)
        raw_items = source.get("items")
        if isinstance(raw_items, list):
            for item in raw_items[:8]:
                if isinstance(item, Mapping):
                    title = str(item.get("title") or "").strip()
                    url = str(item.get("url") or "").strip()
                    published_at = _canonical_news_timestamp(item.get("published_at"))
                    if not title or not url or published_at is None:
                        continue
                    if parse_utc(published_at) > parse_utc(decision_at):
                        continue
                    frozen_metadata = {
                        "title": title,
                        "url": url,
                        "published_at": published_at,
                        "source": str(item.get("source") or "").strip(),
                        "retrieved_at": retrieved_at,
                    }
                    metadata_content_hash = digest_json(frozen_metadata)
                    frozen_metadata.update(
                        {
                            "metadata_content_hash": metadata_content_hash,
                            "news_item_id": "NEWS-" + metadata_content_hash[:20],
                            "authority": "PUBLIC_DISCOVERY_METADATA",
                            "content_boundary": (
                                "HASH_BINDS_FROZEN_HEADLINE_METADATA_NOT_ARTICLE_BODY"
                            ),
                        }
                    )
                    items.append(frozen_metadata)
    return {
        "status": "METADATA_AVAILABLE" if items else UNKNOWN,
        "headline_metadata": items,
        "boundary": "HEADLINES_ARE_CONTEXT_NOT_SENTIMENT_OR_CAUSAL_DIRECTION_TRUTH",
    }


def _symbol_analysis(
    symbol_snapshot: Mapping[str, Any],
    news_snapshot: Mapping[str, Any],
    config: Mapping[str, Any],
    decision_at: str,
) -> dict[str, Any]:
    measurement = _measurement_snapshot(symbol_snapshot)
    state = _multi_scale_state(measurement)
    structural = _structural_position(measurement, state)
    phi = _phi_competition(measurement, state, structural)
    actors = _actor_behavior_hypotheses(measurement)
    result: dict[str, Any] = {
        "symbol": measurement["symbol"],
        "measurement_snapshot": measurement,
        "multi_scale_state_belief": state,
        "structural_position": structural,
        "phi_competition": phi,
        "actor_behavior_hypotheses": actors,
        "news_context": _news_context(
            news_snapshot,
            str(measurement["symbol"]),
            decision_at,
        ),
        "action_geometry_candidates": _geometry_candidates(measurement, config),
        "method_status": EXPERIMENTAL,
        "execution_scope": PAPER_ONLY,
    }
    result["symbol_analysis_id"] = "SA-" + digest_json(result)[:20]
    return result


def _canonical_decision_at(
    decision_at: str | datetime | None, market_snapshot: Mapping[str, Any]
) -> str:
    if isinstance(decision_at, datetime):
        return iso_utc(decision_at)
    if isinstance(decision_at, str):
        parse_utc(decision_at)
        return decision_at
    observed = market_snapshot.get("observed_at")
    if not isinstance(observed, str):
        raise TheoryPaperError("decision_at or market observed_at is required")
    parse_utc(observed)
    return observed


def _frozen_active_method_delta(
    config: Mapping[str, Any],
    cycle_id: str,
) -> dict[str, str] | str:
    raw = config.get("active_method_delta")
    if raw in (None, UNKNOWN):
        return UNKNOWN
    if not isinstance(raw, Mapping):
        raise TheoryPaperError("active_method_delta must be an object")
    required = {
        "id",
        "version",
        "effective_cycle",
        "proposed_method_delta",
        "falsification_test",
    }
    if set(raw) != required:
        raise TheoryPaperError(
            "active_method_delta must contain exactly " + ",".join(sorted(required))
        )
    frozen: dict[str, str] = {}
    for key in sorted(required):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TheoryPaperError(f"active_method_delta.{key} must be a nonempty string")
        frozen[key] = value.strip()
    if frozen["effective_cycle"] != cycle_id:
        raise TheoryPaperError("active_method_delta.effective_cycle must equal cycle_id")
    return frozen


def _frozen_decision_authority(config: Mapping[str, Any]) -> dict[str, str]:
    raw = config.get("decision_authority")
    if raw is None:
        raw = {
            "automation_prompt_sha256": digest_json(
                {
                    "schema": "theory-paper-agent-decision.v1",
                    "binding": "LOCAL_TEMPLATE_UNBOUND_TO_EXTERNAL_AUTOMATION",
                }
            ),
            "path": "BUILT_IN_THEORY_DECISION_TEMPLATE",
            "theory_authority_digest": digest_json(
                {"theory_authority": "NEW_THEORY_PRACTICE_V1_EXPERIMENTAL"}
            ),
        }
    if not isinstance(raw, Mapping):
        raise TheoryPaperError("decision_authority must be an object")
    required = {
        "automation_prompt_sha256",
        "path",
        "theory_authority_digest",
    }
    if set(raw) != required:
        raise TheoryPaperError(
            "decision_authority must contain exactly " + ",".join(sorted(required))
        )
    frozen = {key: str(raw.get(key) or "").strip() for key in sorted(required)}
    if not frozen["path"]:
        raise TheoryPaperError("decision_authority.path must be a nonempty string")
    for key in ("automation_prompt_sha256", "theory_authority_digest"):
        if re.fullmatch(r"[0-9a-f]{64}", frozen[key]) is None:
            raise TheoryPaperError(f"decision_authority.{key} must be a sha256 hex digest")
    return frozen


def _safe_portfolio_context(portfolio_state: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(portfolio_state, Mapping):
        return {
            "provided": False,
            "state_digest": UNKNOWN,
            "valid_hours_without_strategy_fill": UNKNOWN,
            "unprotected_lot_ids": [],
            "review_required_order_ids": [],
            "open_lot_count": 0,
            "open_order_count": 0,
            "boundary": "NO_PORTFOLIO_CONTEXT_PROVIDED",
        }
    lots = portfolio_state.get("lots")
    lot_rows = [row for row in lots if isinstance(row, Mapping)] if isinstance(lots, list) else []
    orders = portfolio_state.get("orders")
    order_rows = [row for row in orders if isinstance(row, Mapping)] if isinstance(orders, list) else []
    open_lots = [row for row in lot_rows if row.get("status") == "OPEN"]
    active_orders = [
        row for row in order_rows if row.get("state") in {"ACTIVE", "REVIEW_REQUIRED"}
    ]
    unprotected = [
        str(row.get("lot_id"))
        for row in open_lots
        if row.get("stop_price") is None or row.get("target_price") is None
    ]
    review_required = [
        str(row.get("order_id"))
        for row in order_rows
        if row.get("state") == "REVIEW_REQUIRED"
    ]
    inactivity = portfolio_state.get("valid_hours_without_strategy_fill")
    if isinstance(inactivity, bool) or not isinstance(inactivity, int) or inactivity < 0:
        inactivity = UNKNOWN
    return {
        "provided": True,
        "state_digest": digest_json(portfolio_state),
        "valid_hours_without_strategy_fill": inactivity,
        "unprotected_lot_ids": sorted(unprotected),
        "review_required_order_ids": sorted(review_required),
        "open_lot_count": len(open_lots),
        "open_order_count": len(active_orders),
        "boundary": (
            "SAFE_COUNTS_AND_IDS_ONLY; CHAOS_FUTURE_SCHEDULE_NOT_EXPOSED; "
            "PORTFOLIO_CONTEXT_DOES_NOT_CHANGE_MEASUREMENT_OR_PHI_SUPPORT"
        ),
    }


def build_cycle_analysis(
    market_snapshot: Mapping[str, Any],
    news_snapshot: Mapping[str, Any] | None = None,
    portfolio_state: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    cycle_id: str | None = None,
    decision_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Build the complete deterministic analysis chain for one paper cycle."""

    if not isinstance(market_snapshot, Mapping):
        raise TheoryPaperError("market_snapshot must be an object")
    raw_symbols = market_snapshot.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise TheoryPaperError("market_snapshot.symbols must be a nonempty list")
    if not all(isinstance(item, Mapping) for item in raw_symbols):
        raise TheoryPaperError("each market symbol snapshot must be an object")
    news = news_snapshot if isinstance(news_snapshot, Mapping) else {}
    settings = config if isinstance(config, Mapping) else {}
    at = _canonical_decision_at(decision_at, market_snapshot)
    identifier = cycle_id or (
        "CYCLE-" + digest_json({"at": at, "market": market_snapshot.get("market_snapshot_digest")})[:16]
    )
    if not isinstance(identifier, str) or not identifier.strip():
        raise TheoryPaperError("cycle_id must be a nonempty string")
    for label, snapshot in (("market", market_snapshot), ("news", news)):
        observed = snapshot.get("observed_at") if isinstance(snapshot, Mapping) else None
        if isinstance(observed, str) and parse_utc(observed) > parse_utc(at):
            raise TheoryPaperError(f"{label} snapshot is from the future")

    symbols = [_symbol_analysis(item, news, settings, at) for item in raw_symbols]
    names = [item["symbol"] for item in symbols]
    if len(set(names)) != len(names):
        raise TheoryPaperError("market snapshot contains duplicate symbols")
    result: dict[str, Any] = {
        "schema_version": "theory-paper-cycle-analysis.v1",
        "cycle_id": identifier,
        "decision_at": at,
        "method_status": EXPERIMENTAL,
        "execution_scope": PAPER_ONLY,
        "theory_authority": "NEW_THEORY_PRACTICE_V1_EXPERIMENTAL",
        "decision_authority": _frozen_decision_authority(settings),
        "market_snapshot_digest": _value(market_snapshot.get("market_snapshot_digest")),
        "news_snapshot_digest": digest_json(news) if news else UNKNOWN,
        "portfolio_context": _safe_portfolio_context(portfolio_state),
        "active_method_delta": _frozen_active_method_delta(settings, identifier),
        "symbols": symbols,
        "failed_market_symbols": _value(market_snapshot.get("failures")),
        "boundaries": [
            "PUBLIC_DATA_ONLY",
            "EXPERIMENTAL_UNCALIBRATED_THEORY",
            "PAPER_ONLY_NO_REAL_ORDER_AUTHORITY",
            "ORDINAL_SUPPORT_IS_NOT_PROBABILITY",
            "ACTOR_BEHAVIOR_IS_INFERENCE_NOT_IDENTITY",
        ],
    }
    result["analysis_digest"] = digest_json(result)
    result["theory_integrity_score"] = score_theory_integrity(result)
    return result


def build_decision_template(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact editable decision shape consumed by ``validate_decision``."""

    symbols = analysis.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise TheoryPaperError("analysis has no symbols")
    symbol_decisions: list[dict[str, Any]] = []
    for symbol_analysis in symbols:
        item = _mapping(symbol_analysis)
        phi = _mapping(item.get("phi_competition"))
        geometries = item.get("action_geometry_candidates")
        measurement = _mapping(item.get("measurement_snapshot"))
        multiscale = _mapping(item.get("multi_scale_state_belief"))
        structural = _mapping(item.get("structural_position"))
        actors = _mapping(item.get("actor_behavior_hypotheses"))
        available_fact_refs = [
            {
                "kind": "MEASUREMENT_SNAPSHOT",
                "id": measurement.get("measurement_snapshot_id"),
            },
            {
                "kind": "STRUCTURAL_POSITION",
                "id": structural.get("structural_position_id"),
            },
        ]
        if analysis.get("news_snapshot_digest") not in (None, UNKNOWN):
            available_fact_refs.append(
                {
                    "kind": "NEWS_SNAPSHOT",
                    "id": analysis.get("news_snapshot_digest"),
                }
            )
        available_inference_refs = [
            {
                "kind": "MULTISCALE_STATE",
                "id": multiscale.get("multi_scale_state_belief_id"),
            },
            {
                "kind": "PHI_COMPETITION",
                "id": phi.get("phi_competition_id"),
            },
            {
                "kind": "ACTOR_BEHAVIOR",
                "id": actors.get("actor_behavior_hypotheses_id"),
            },
            *(
                [
                    {
                        "kind": "ACTION_GEOMETRY",
                        "id": candidate.get("geometry_candidate_id"),
                    }
                    for candidate in geometries
                    if isinstance(candidate, Mapping)
                ]
                if isinstance(geometries, list)
                else []
            ),
        ]
        symbol_decisions.append(
            {
                "symbol": item.get("symbol"),
                "action": "REQUIRED",
                "execution_intent": "NO_NEW_RISK",
                "selected_phi_id": "REQUIRED",
                "alternative_phi_ids": [],
                "analysis_narrative_zh": "REQUIRED",
                "behavior_hypotheses_zh": "REQUIRED",
                "future_force_path_zh": "REQUIRED",
                "thesis": "REQUIRED",
                "fact_refs": [],
                "inference_refs": [],
                "hard_falsifier": "REQUIRED",
                "support_predicate": {
                    "observable_id": "REQUIRED",
                    "operator": "REQUIRED",
                    "value": "REQUIRED",
                },
                "falsifier_predicate": {
                    "observable_id": "REQUIRED",
                    "operator": "REQUIRED",
                    "value": "REQUIRED",
                },
                "next_observations": [],
                "expiry_at": "REQUIRED_UTC_Z",
                "geometry_candidate_id": "REQUIRED_FOR_NEW_RISK_OTHERWISE_UNKNOWN",
                "order": {
                    "order_type": "MARKET_OR_LIMIT_OR_UNKNOWN",
                    "side": "BUY_OR_SELL_OR_UNKNOWN",
                    "limit_price": UNKNOWN,
                    "notional_usdt": UNKNOWN,
                    "stop_loss": UNKNOWN,
                    "take_profit": UNKNOWN,
                },
                "abstention_reason_code": UNKNOWN,
                "market_actionability": "ACTIONABLE_OR_DATA_INVALID_OR_RISK_VETO",
                "active_probe_plan": False,
                "available_fact_refs": available_fact_refs,
                "available_inference_refs": available_inference_refs,
                "allowed_phi_ids": _value(phi.get("finite_registry")),
                "available_geometry_candidate_ids": [
                    candidate.get("geometry_candidate_id")
                    for candidate in geometries
                    if isinstance(candidate, Mapping)
                ]
                if isinstance(geometries, list)
                else [],
            }
        )
    return {
        "schema_version": "theory-paper-agent-decision.v1",
        "analysis_digest": analysis.get("analysis_digest"),
        "cycle_id": analysis.get("cycle_id"),
        "decision_at": analysis.get("decision_at"),
        "execution_scope": PAPER_ONLY,
        "allowed_actions": list(ALLOWED_ACTIONS),
        "executive_summary_zh": "REQUIRED",
        "portfolio_rationale_zh": "REQUIRED",
        "news_evidence": [],
        "method_observations": [],
        "agent_identity": {
            "agent_role": "REQUIRED_RUNTIME_AGENT_ROLE",
            "model_identity": "REQUIRED_RUNTIME_MODEL_IDENTITY",
            "prompt_binding_sha256": _mapping(
                analysis.get("decision_authority")
            ).get("automation_prompt_sha256"),
        },
        "active_method_delta": copy.deepcopy(analysis.get("active_method_delta", UNKNOWN)),
        "method_delta_execution": (
            {
                "method_delta_id": _mapping(analysis.get("active_method_delta")).get("id"),
                "execution_steps": ["REQUIRED_CURRENT_CYCLE_STEP"],
                "acceptance_criteria": ["REQUIRED_OBSERVABLE_ACCEPTANCE_CRITERION"],
                "falsification_observation": "REQUIRED_CURRENT_CYCLE_OBSERVATION",
            }
            if isinstance(analysis.get("active_method_delta"), Mapping)
            else UNKNOWN
        ),
        "symbol_decisions": symbol_decisions,
        "allowed_portfolio_action_types": list(PORTFOLIO_ACTIONS),
        "portfolio_actions": [],
        "agent_attestation": {
            "no_real_order": True,
            "ordinal_not_probability": True,
            "actor_claims_not_identity": True,
            "thesis_frozen_before_paper_action": True,
        },
    }


def _is_future_utc(value: Any, decision_at: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return parse_utc(value) > parse_utc(decision_at)
    except TheoryPaperError:
        return False


def _same_finite(left: Any, right: Any, *, tolerance: float = 1e-8) -> bool:
    left_value = _finite(left)
    right_value = _finite(right)
    if left_value is None or right_value is None:
        return left_value is None and right_value is None
    return math.isclose(
        left_value,
        right_value,
        rel_tol=tolerance,
        abs_tol=tolerance,
    )


def _net_reward_risk(
    *,
    action_type: str,
    order_type: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    settings: Mapping[str, Any],
) -> float | None:
    policy = _mapping(settings.get("risk_policy"))
    maker_fee = _finite(policy.get("default_maker_fee_rate"))
    taker_fee = _finite(policy.get("default_taker_fee_rate"))
    market_slippage = _finite(policy.get("default_market_slippage_bps"))
    stop_slippage = _finite(policy.get("default_stop_slippage_bps"))
    maker_fee = 0.0002 if maker_fee is None else maker_fee
    taker_fee = 0.0005 if taker_fee is None else taker_fee
    market_slippage = 2.0 if market_slippage is None else market_slippage
    stop_slippage = 3.0 if stop_slippage is None else stop_slippage
    is_long = action_type in {"OPEN_LONG", "ADD_LONG"}
    entry_fill = entry_price
    if order_type == "MARKET":
        entry_fill *= 1.0 + (
            market_slippage / 10000.0
            if is_long
            else -market_slippage / 10000.0
        )
    stop_fill = stop_price * (
        1.0 - stop_slippage / 10000.0
        if is_long
        else 1.0 + stop_slippage / 10000.0
    )
    price_risk = entry_fill - stop_fill if is_long else stop_fill - entry_fill
    price_reward = (
        target_price - entry_fill if is_long else entry_fill - target_price
    )
    entry_fee = entry_fill * (
        taker_fee if order_type == "MARKET" else maker_fee
    )
    stop_fee = stop_fill * taker_fee
    target_fee = target_price * maker_fee
    net_risk = price_risk + entry_fee + stop_fee
    net_reward = price_reward - entry_fee - target_fee
    if net_risk <= 0 or net_reward <= 0:
        return None
    return net_reward / net_risk


def _valid_observation_predicate(value: Any) -> bool:
    predicate = _mapping(value)
    observable = predicate.get("observable_id")
    operator = predicate.get("operator")
    expected = predicate.get("value")
    if observable not in OBSERVABLE_IDS or operator not in PREDICATE_OPERATORS:
        return False
    if isinstance(expected, (dict, list)) or expected is None or expected == "REQUIRED":
        return False
    if operator in {"GT", "GTE", "LT", "LTE"} and _finite(expected) is None:
        return False
    return True


def _reference_registries(
    symbol_analysis: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    measurement = _mapping(symbol_analysis.get("measurement_snapshot"))
    multiscale = _mapping(symbol_analysis.get("multi_scale_state_belief"))
    structural = _mapping(symbol_analysis.get("structural_position"))
    phi = _mapping(symbol_analysis.get("phi_competition"))
    actors = _mapping(symbol_analysis.get("actor_behavior_hypotheses"))
    facts = {
        ("MEASUREMENT_SNAPSHOT", str(measurement.get("measurement_snapshot_id"))),
        ("STRUCTURAL_POSITION", str(structural.get("structural_position_id"))),
    }
    news_digest = analysis.get("news_snapshot_digest")
    if news_digest not in (None, UNKNOWN):
        facts.add(("NEWS_SNAPSHOT", str(news_digest)))
    inferences = {
        ("MULTISCALE_STATE", str(multiscale.get("multi_scale_state_belief_id"))),
        ("PHI_COMPETITION", str(phi.get("phi_competition_id"))),
        ("ACTOR_BEHAVIOR", str(actors.get("actor_behavior_hypotheses_id"))),
    }
    for candidate in symbol_analysis.get("action_geometry_candidates", []):
        if isinstance(candidate, Mapping):
            inferences.add(
                ("ACTION_GEOMETRY", str(candidate.get("geometry_candidate_id")))
            )
    return facts, inferences


def _valid_typed_refs(
    value: Any,
    registry: set[tuple[str, str]],
    *,
    require_nonempty: bool,
) -> bool:
    if not isinstance(value, list) or (require_nonempty and not value):
        return False
    normalized: list[tuple[str, str]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {"kind", "id"}:
            return False
        reference = (str(raw.get("kind")), str(raw.get("id")))
        if reference not in registry:
            return False
        normalized.append(reference)
    return len(normalized) == len(set(normalized))


def _contains_forbidden_secret_material(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = "".join(
                character for character in str(key).lower() if character.isalnum()
            )
            if normalized_key in {"live", "token"}:
                return True
            if any(
                normalized_key.startswith(prefix)
                for prefix in _FORBIDDEN_DECISION_KEY_PREFIXES
            ):
                return True
            if _contains_forbidden_secret_material(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_forbidden_secret_material(child) for child in value)
    if isinstance(value, str):
        return any(pattern.search(value) is not None for pattern in _SECRET_VALUE_PATTERNS)
    return False


def _frozen_news_by_symbol(
    analysis: Mapping[str, Any],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    registry: dict[str, dict[str, Mapping[str, Any]]] = {}
    for raw_symbol in analysis.get("symbols", []):
        symbol_analysis = _mapping(raw_symbol)
        symbol = symbol_analysis.get("symbol")
        if not isinstance(symbol, str):
            continue
        items = _mapping(symbol_analysis.get("news_context")).get("headline_metadata")
        if not isinstance(items, list):
            continue
        symbol_items: dict[str, Mapping[str, Any]] = {}
        for item in items:
            if isinstance(item, Mapping) and isinstance(item.get("news_item_id"), str):
                symbol_items[str(item["news_item_id"])] = item
        registry[symbol] = symbol_items
    return registry


def _official_source_url_allowed(symbol: str, source_url: str) -> bool:
    try:
        parsed = urlparse(source_url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    allowed = GLOBAL_OFFICIAL_DOMAINS | SYMBOL_OFFICIAL_DOMAINS.get(
        symbol,
        frozenset(),
    )
    return (
        parsed.scheme == "https"
        and bool(hostname)
        and any(
            hostname == domain or hostname.endswith("." + domain)
            for domain in allowed
        )
    )


def _nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def validate_decision(
    decision: Mapping[str, Any],
    analysis: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail closed and return normalized ``actions`` for the paper portfolio."""

    errors: list[str] = []
    warnings: list[str] = []
    settings = config if isinstance(config, Mapping) else {}
    minimum_rr = (
        _finite(_mapping(settings.get("risk_policy")).get("minimum_reward_risk"))
        or _finite(settings.get("minimum_reward_risk"))
        or 1.5
    )
    if not isinstance(decision, Mapping):
        return {
            "valid": False,
            "errors": ["DECISION_NOT_OBJECT"],
            "warnings": [],
            "normalized_decision": None,
            "orchestration_gate": {
                "status": "BLOCKED_INVALID_DECISION",
                "satisfied": False,
            },
        }
    analysis_decision_at = analysis.get("decision_at")
    try:
        if not isinstance(analysis_decision_at, str):
            raise TheoryPaperError("missing analysis decision_at")
        parse_utc(analysis_decision_at)
    except TheoryPaperError:
        errors.append("ANALYSIS_DECISION_AT_INVALID")
        analysis_decision_at = "1970-01-01T00:00:00Z"
    supplied_decision_at = decision.get("decision_at")
    if not isinstance(supplied_decision_at, str):
        errors.append("DECISION_AT_REQUIRED")
    else:
        try:
            parse_utc(supplied_decision_at)
        except TheoryPaperError:
            errors.append("DECISION_AT_INVALID")
        if supplied_decision_at != analysis_decision_at:
            errors.append("DECISION_AT_MISMATCH")
    if decision.get("execution_scope") != PAPER_ONLY:
        errors.append("EXECUTION_SCOPE_NOT_PAPER_ONLY")
    if decision.get("analysis_digest") != analysis.get("analysis_digest"):
        errors.append("ANALYSIS_DIGEST_MISMATCH")
    if decision.get("cycle_id") != analysis.get("cycle_id"):
        errors.append("CYCLE_ID_MISMATCH")

    if _contains_forbidden_secret_material(decision):
        errors.append("LIVE_OR_CREDENTIAL_FIELD_FORBIDDEN")

    agent_identity = decision.get("agent_identity")
    expected_prompt_binding = _mapping(analysis.get("decision_authority")).get(
        "automation_prompt_sha256"
    )
    if (
        not isinstance(agent_identity, Mapping)
        or set(agent_identity)
        != {"agent_role", "model_identity", "prompt_binding_sha256"}
        or not isinstance(agent_identity.get("agent_role"), str)
        or not agent_identity.get("agent_role", "").strip()
        or str(agent_identity.get("agent_role", "")).startswith("REQUIRED_")
        or not isinstance(agent_identity.get("model_identity"), str)
        or not agent_identity.get("model_identity", "").strip()
        or str(agent_identity.get("model_identity", "")).startswith("REQUIRED_")
    ):
        errors.append("AGENT_IDENTITY_REQUIRED")
    if (
        not isinstance(expected_prompt_binding, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_prompt_binding) is None
        or _mapping(agent_identity).get("prompt_binding_sha256")
        != expected_prompt_binding
    ):
        errors.append("AGENT_PROMPT_BINDING_MISMATCH")

    for field in ("executive_summary_zh", "portfolio_rationale_zh"):
        value = decision.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or value.strip() == "REQUIRED"
        ):
            errors.append(f"{field.upper()}_REQUIRED")
    for field in ("news_evidence", "method_observations"):
        if not isinstance(decision.get(field), list):
            errors.append(f"{field.upper()}_NOT_LIST")
    method_observations = decision.get("method_observations")
    if isinstance(method_observations, list) and (
        not method_observations
        or any(
            not isinstance(item, str) or not item.strip()
            for item in method_observations
        )
    ):
        errors.append("METHOD_OBSERVATIONS_REQUIRE_NONEMPTY_STRINGS")

    active_method_delta = analysis.get("active_method_delta", UNKNOWN)
    if isinstance(active_method_delta, Mapping):
        if decision.get("active_method_delta") != active_method_delta:
            errors.append("ACTIVE_METHOD_DELTA_MISMATCH")
        method_execution = decision.get("method_delta_execution")
        required_execution_keys = {
            "method_delta_id",
            "execution_steps",
            "acceptance_criteria",
            "falsification_observation",
        }
        if (
            not isinstance(method_execution, Mapping)
            or set(method_execution) != required_execution_keys
            or method_execution.get("method_delta_id") != active_method_delta.get("id")
            or not _nonempty_string_list(method_execution.get("execution_steps"))
            or not _nonempty_string_list(method_execution.get("acceptance_criteria"))
            or not isinstance(method_execution.get("falsification_observation"), str)
            or not method_execution.get("falsification_observation", "").strip()
            or str(method_execution.get("falsification_observation", "")).startswith(
                "REQUIRED_"
            )
            or any(
                str(item).startswith("REQUIRED_")
                for field in ("execution_steps", "acceptance_criteria")
                for item in method_execution.get(field, [])
            )
        ):
            errors.append("ACTIVE_METHOD_DELTA_EXECUTION_PLAN_REQUIRED")
    elif decision.get("active_method_delta", UNKNOWN) != UNKNOWN:
        errors.append("UNFROZEN_ACTIVE_METHOD_DELTA_FORBIDDEN")
    elif decision.get("method_delta_execution", UNKNOWN) != UNKNOWN:
        errors.append("UNFROZEN_METHOD_DELTA_EXECUTION_FORBIDDEN")

    news_evidence = decision.get("news_evidence")
    if isinstance(news_evidence, list):
        common_news_keys = {
            "symbol",
            "source_url",
            "published_at",
            "claim_zh",
            "authority",
            "causal_status",
            "evidence_origin",
            "title",
            "retrieved_at",
            "content_hash",
        }
        frozen_news = _frozen_news_by_symbol(analysis)
        for index, item in enumerate(news_evidence):
            prefix = f"NEWS_EVIDENCE_{index}"
            if not isinstance(item, Mapping):
                errors.append(f"NEWS_EVIDENCE_{index}:INVALID_TYPED_EVIDENCE")
                continue
            authority = item.get("authority")
            required_keys = (
                common_news_keys | {"frozen_news_item_id"}
                if authority == "PUBLIC_DISCOVERY_METADATA"
                else common_news_keys
            )
            if (
                set(item) != required_keys
                or authority not in {"OFFICIAL_PRIMARY", "PUBLIC_DISCOVERY_METADATA"}
                or item.get("causal_status")
                not in {
                    "CONTEXT_ONLY",
                    "TEMPORAL_HYPOTHESIS_NOT_CAUSAL_PROOF",
                }
                or item.get("symbol") not in EXPERIMENT_SYMBOLS
                or not str(item.get("source_url", "")).startswith("https://")
                or not isinstance(item.get("title"), str)
                or not item.get("title", "").strip()
                or not isinstance(item.get("claim_zh"), str)
                or not item.get("claim_zh", "").strip()
                or re.fullmatch(r"[0-9a-f]{64}", str(item.get("content_hash", "")))
                is None
            ):
                errors.append(f"{prefix}:INVALID_TYPED_EVIDENCE")
                continue
            try:
                published = parse_utc(str(item.get("published_at")))
            except TheoryPaperError:
                errors.append(f"{prefix}:INVALID_PUBLISHED_AT")
                published = None
            try:
                retrieved = parse_utc(str(item.get("retrieved_at")))
            except TheoryPaperError:
                errors.append(f"{prefix}:INVALID_RETRIEVED_AT")
                retrieved = None
            decision_time = parse_utc(analysis_decision_at)
            if published is not None and published > decision_time:
                errors.append(f"{prefix}:PUBLISHED_AFTER_DECISION")
            if retrieved is not None and retrieved > decision_time:
                errors.append(f"{prefix}:RETRIEVED_AFTER_DECISION")
            if (
                published is not None
                and retrieved is not None
                and published > retrieved
            ):
                errors.append(f"{prefix}:PUBLISHED_AFTER_RETRIEVAL")

            symbol = str(item.get("symbol"))
            symbol_news = frozen_news.get(symbol, {})
            matching_discovery_urls = {
                str(frozen.get("url"))
                for frozen in symbol_news.values()
                if isinstance(frozen, Mapping)
            }
            if authority == "PUBLIC_DISCOVERY_METADATA":
                if item.get("evidence_origin") != "FROZEN_PUBLIC_DISCOVERY":
                    errors.append(f"{prefix}:INVALID_DISCOVERY_ORIGIN")
                frozen = symbol_news.get(str(item.get("frozen_news_item_id")))
                expected = {
                    "source_url": _mapping(frozen).get("url"),
                    "published_at": _mapping(frozen).get("published_at"),
                    "title": _mapping(frozen).get("title"),
                    "retrieved_at": _mapping(frozen).get("retrieved_at"),
                    "content_hash": _mapping(frozen).get("metadata_content_hash"),
                }
                if not isinstance(frozen, Mapping) or any(
                    item.get(key) != expected_value
                    for key, expected_value in expected.items()
                ):
                    errors.append(f"{prefix}:FROZEN_DISCOVERY_BINDING_MISMATCH")
            else:
                if item.get("evidence_origin") != "EXTERNAL_OFFICIAL_VERIFICATION":
                    errors.append(f"{prefix}:INVALID_OFFICIAL_ORIGIN")
                if not _official_source_url_allowed(
                    symbol,
                    str(item.get("source_url") or ""),
                ):
                    errors.append(f"{prefix}:OFFICIAL_SOURCE_DOMAIN_NOT_ALLOWED")
                if item.get("source_url") in matching_discovery_urls:
                    errors.append(
                        f"{prefix}:OFFICIAL_AUTHORITY_CANNOT_RECLASSIFY_DISCOVERY"
                    )

    attestation = _mapping(decision.get("agent_attestation"))
    for key in (
        "no_real_order",
        "ordinal_not_probability",
        "actor_claims_not_identity",
        "thesis_frozen_before_paper_action",
    ):
        if attestation.get(key) is not True:
            errors.append(f"ATTESTATION_FALSE:{key}")

    symbol_analyses = {
        item.get("symbol"): item
        for item in analysis.get("symbols", [])
        if isinstance(item, Mapping)
    }
    raw_symbol_decisions = decision.get("symbol_decisions")
    if not isinstance(raw_symbol_decisions, list):
        raw_symbol_decisions = []
        errors.append("SYMBOL_DECISIONS_NOT_LIST")
    seen: set[str] = set()
    normalized_symbol_decisions: list[dict[str, Any]] = []
    for index, raw_action in enumerate(raw_symbol_decisions):
        prefix = f"SYMBOL_DECISION_{index}"
        action = _mapping(raw_action)
        symbol = action.get("symbol")
        if not isinstance(symbol, str) or symbol not in symbol_analyses:
            errors.append(f"{prefix}:UNKNOWN_SYMBOL")
            continue
        if symbol in seen:
            errors.append(f"{prefix}:DUPLICATE_SYMBOL")
            continue
        seen.add(symbol)
        action_type = action.get("action")
        if action_type not in ALLOWED_ACTIONS:
            errors.append(f"{prefix}:INVALID_ACTION")
        execution_intent = action.get("execution_intent")
        if execution_intent not in EXECUTION_INTENT_VALUES:
            errors.append(f"{prefix}:INVALID_EXECUTION_INTENT")
        elif action_type in NEW_RISK_ACTIONS:
            if execution_intent not in {"EXECUTE_NOW", "PLAN_ONLY"}:
                errors.append(f"{prefix}:NEW_RISK_REQUIRES_EXECUTION_INTENT")
        elif execution_intent != "NO_NEW_RISK":
            errors.append(f"{prefix}:NON_RISK_EXECUTION_INTENT_MUST_BE_NO_NEW_RISK")
        market_actionability = action.get("market_actionability")
        if market_actionability not in MARKET_ACTIONABILITY_VALUES:
            errors.append(f"{prefix}:INVALID_MARKET_ACTIONABILITY")
        active_probe_plan = action.get("active_probe_plan")
        if type(active_probe_plan) is not bool:
            errors.append(f"{prefix}:ACTIVE_PROBE_PLAN_MUST_BE_BOOLEAN")
        elif active_probe_plan and (
            market_actionability != "ACTIONABLE"
            or action_type not in NEW_RISK_ACTIONS
            or execution_intent not in {"EXECUTE_NOW", "PLAN_ONLY"}
        ):
            errors.append(f"{prefix}:ACTIVE_PROBE_PLAN_INCONSISTENT")
        if action_type in NEW_RISK_ACTIONS and market_actionability != "ACTIONABLE":
            errors.append(f"{prefix}:NEW_RISK_REQUIRES_ACTIONABLE_MARKET")
        phi_id = action.get("selected_phi_id")
        phi_registry = _mapping(symbol_analyses[symbol].get("phi_competition")).get(
            "finite_registry"
        )
        if not isinstance(phi_registry, list) or phi_id not in phi_registry:
            errors.append(f"{prefix}:INVALID_SELECTED_PHI")
        alternatives = action.get("alternative_phi_ids")
        if (
            not isinstance(alternatives, list)
            or not alternatives
            or len(alternatives) != len(set(alternatives))
            or phi_id in alternatives
            or any(candidate not in phi_registry for candidate in alternatives)
        ):
            errors.append(f"{prefix}:INVALID_ALTERNATIVE_PHI")
        for field in (
            "analysis_narrative_zh",
            "behavior_hypotheses_zh",
            "future_force_path_zh",
        ):
            value = action.get(field)
            if (
                not isinstance(value, str)
                or not value.strip()
                or value.strip() == "REQUIRED"
            ):
                errors.append(f"{prefix}:{field.upper()}_REQUIRED")
        if not isinstance(action.get("thesis"), str) or not action.get("thesis", "").strip():
            errors.append(f"{prefix}:THESIS_REQUIRED")
        fact_registry, inference_registry = _reference_registries(
            symbol_analyses[symbol],
            analysis,
        )
        if not _valid_typed_refs(
            action.get("fact_refs"),
            fact_registry,
            require_nonempty=True,
        ):
            errors.append(f"{prefix}:VALID_TYPED_FACT_REFS_REQUIRED")
        if not _valid_typed_refs(
            action.get("inference_refs"),
            inference_registry,
            require_nonempty=True,
        ):
            errors.append(f"{prefix}:VALID_TYPED_INFERENCE_REFS_REQUIRED")
        if (
            not isinstance(action.get("next_observations"), list)
            or not action.get("next_observations")
        ):
            errors.append(f"{prefix}:NEXT_OBSERVATIONS_REQUIRED")
        if not isinstance(action.get("hard_falsifier"), str) or not action.get(
            "hard_falsifier", ""
        ).strip():
            errors.append(f"{prefix}:HARD_FALSIFIER_REQUIRED")
        if not _valid_observation_predicate(action.get("support_predicate")):
            errors.append(f"{prefix}:VALID_SUPPORT_PREDICATE_REQUIRED")
        if not _valid_observation_predicate(action.get("falsifier_predicate")):
            errors.append(f"{prefix}:VALID_FALSIFIER_PREDICATE_REQUIRED")
        if not _is_future_utc(action.get("expiry_at"), analysis_decision_at):
            errors.append(f"{prefix}:VALID_FUTURE_EXPIRY_REQUIRED")

        geometry_id = action.get("geometry_candidate_id")
        geometries = {
            item.get("geometry_candidate_id"): item
            for item in symbol_analyses[symbol].get("action_geometry_candidates", [])
            if isinstance(item, Mapping)
        }
        order = _mapping(action.get("order"))
        if action_type in NEW_RISK_ACTIONS:
            geometry = geometries.get(geometry_id)
            if not isinstance(geometry, Mapping) or geometry.get("status") != "RESEARCH_READY":
                errors.append(f"{prefix}:READY_GEOMETRY_REQUIRED")
            stop = _finite(order.get("stop_loss"))
            target = _finite(order.get("take_profit"))
            notional = _finite(order.get("notional_usdt"))
            if stop is None or target is None or notional is None or notional <= 0:
                errors.append(f"{prefix}:BOUNDED_ORDER_GEOMETRY_REQUIRED")
            expected_side = (
                "BUY" if action_type in {"OPEN_LONG", "ADD_LONG"} else "SELL"
            )
            if order.get("side") != expected_side:
                errors.append(f"{prefix}:ORDER_SIDE_DOES_NOT_MATCH_ACTION")
            order_type = str(order.get("order_type") or "").upper()
            if order_type not in {"MARKET", "LIMIT"}:
                errors.append(f"{prefix}:MARKET_OR_LIMIT_ORDER_REQUIRED")
            entry = _finite(order.get("limit_price"))
            if entry is None and isinstance(geometry, Mapping):
                zone = _mapping(geometry.get("entry_zone"))
                low, high = _finite(zone.get("low")), _finite(zone.get("high"))
                if order_type == "MARKET":
                    entry = _finite(
                        _mapping(symbol_analyses[symbol].get("measurement_snapshot")).get(
                            "reference_price"
                        )
                    )
                elif low is not None and high is not None:
                    entry = (low + high) / 2.0
            if isinstance(geometry, Mapping):
                zone = _mapping(geometry.get("entry_zone"))
                low, high = _finite(zone.get("low")), _finite(zone.get("high"))
                geometry_side = geometry.get("side")
                if geometry_side != (
                    "LONG" if expected_side == "BUY" else "SHORT"
                ):
                    errors.append(f"{prefix}:GEOMETRY_SIDE_DOES_NOT_MATCH_ACTION")
                if (
                    entry is None
                    or low is None
                    or high is None
                    or not low - 1e-8 <= entry <= high + 1e-8
                ):
                    errors.append(f"{prefix}:ENTRY_OUTSIDE_GEOMETRY_ZONE")
                if not _same_finite(stop, geometry.get("stop_loss")):
                    errors.append(f"{prefix}:STOP_DOES_NOT_MATCH_GEOMETRY")
                if not _same_finite(target, geometry.get("take_profit")):
                    errors.append(f"{prefix}:TARGET_DOES_NOT_MATCH_GEOMETRY")
            if entry is not None and stop is not None and target is not None:
                risk = entry - stop if action_type in {"OPEN_LONG", "ADD_LONG"} else stop - entry
                reward = target - entry if action_type in {"OPEN_LONG", "ADD_LONG"} else entry - target
                if risk <= 0 or reward <= 0:
                    errors.append(f"{prefix}:REWARD_RISK_OR_DIRECTION_INVALID")
                else:
                    net_rr = _net_reward_risk(
                        action_type=str(action_type),
                        order_type=order_type,
                        entry_price=entry,
                        stop_price=stop,
                        target_price=target,
                        settings=settings,
                    )
                    if net_rr is None or net_rr + 1e-12 < minimum_rr:
                        errors.append(f"{prefix}:MINIMUM_NET_REWARD_RISK_NOT_MET")
        elif geometry_id not in (None, UNKNOWN) and geometry_id not in geometries:
            warnings.append(f"{prefix}:NON_RISK_GEOMETRY_ID_UNKNOWN")

        normalized_symbol_decisions.append(
            {
                key: copy.deepcopy(action.get(key))
                for key in (
                    "symbol",
                    "action",
                    "execution_intent",
                    "selected_phi_id",
                    "alternative_phi_ids",
                    "analysis_narrative_zh",
                    "behavior_hypotheses_zh",
                    "future_force_path_zh",
                    "thesis",
                    "fact_refs",
                    "inference_refs",
                    "hard_falsifier",
                    "support_predicate",
                    "falsifier_predicate",
                    "next_observations",
                    "expiry_at",
                    "geometry_candidate_id",
                    "order",
                    "abstention_reason_code",
                    "market_actionability",
                    "active_probe_plan",
                )
            }
        )
    missing = sorted(set(symbol_analyses) - seen)
    if missing:
        errors.append("MISSING_SYMBOL_DECISIONS:" + ",".join(missing))

    raw_portfolio_actions = decision.get("portfolio_actions")
    if not isinstance(raw_portfolio_actions, list):
        raw_portfolio_actions = []
        errors.append("PORTFOLIO_ACTIONS_NOT_LIST")
    normalized_portfolio_actions: list[dict[str, Any]] = []
    new_risk_actions_by_symbol: dict[str, int] = {}
    executed_probe_symbols: set[str] = set()
    selected_by_symbol = {
        str(item.get("symbol")): item
        for item in normalized_symbol_decisions
    }
    for index, raw_operation in enumerate(raw_portfolio_actions):
        prefix = f"PORTFOLIO_ACTION_{index}"
        if not isinstance(raw_operation, Mapping):
            errors.append(f"{prefix}:NOT_OBJECT")
            continue
        supplied_operation = copy.deepcopy(dict(raw_operation))
        kind = str(supplied_operation.get("type", "")).upper()
        allowed_operation_fields = {
            "UPDATE_PROTECTION": {
                "type",
                "symbol",
                "lot_id",
                "stop_price",
                "target_price",
                "reason",
            },
            "KEEP_ORDER": {
                "type",
                "order_id",
                "symbol",
                "side",
                "limit_price",
                "notional_usdt",
                "stop_price",
                "target_price",
                "hypothesis_id",
                "geometry_candidate_id",
                "reduce_only",
                "attribution",
                "risk_authorization",
                "probe",
                "reason",
            },
            "REPLACE_ORDER": {"type", "order_id", "replacement", "reason"},
            "CANCEL_ORDER": {"type", "order_id", "reason"},
            "PLACE_LIMIT": {
                "type",
                "symbol",
                "side",
                "limit_price",
                "notional_usdt",
                "stop_price",
                "target_price",
                "hypothesis_id",
                "geometry_candidate_id",
                "reduce_only",
                "attribution",
                "risk_authorization",
                "probe",
                "reason",
            },
            "MARKET": {
                "type",
                "symbol",
                "side",
                "notional_usdt",
                "limit_price",
                "stop_price",
                "target_price",
                "hypothesis_id",
                "geometry_candidate_id",
                "reduce_only",
                "attribution",
                "risk_authorization",
                "probe",
                "origin",
                "reason",
            },
            "CLOSE": {
                "type",
                "symbol",
                "notional_usdt",
                "attribution",
                "hypothesis_id",
                "reason",
            },
            "HOLD": {"type", "reason"},
        }
        if kind not in PORTFOLIO_ACTIONS:
            errors.append(f"{prefix}:INVALID_TYPE")
        allowed_fields = allowed_operation_fields.get(kind, {"type"})
        unknown_fields = sorted(set(supplied_operation) - allowed_fields)
        if unknown_fields:
            errors.append(
                f"{prefix}:UNKNOWN_FIELDS:" + ",".join(str(item) for item in unknown_fields)
            )
        operation = {
            key: copy.deepcopy(value)
            for key, value in supplied_operation.items()
            if key in allowed_fields
        }
        operation["type"] = kind
        if _contains_forbidden_secret_material(supplied_operation):
            errors.append(f"{prefix}:LIVE_OR_CREDENTIAL_FIELD_FORBIDDEN")
        symbol = operation.get("symbol")
        if symbol is not None and symbol not in symbol_analyses:
            errors.append(f"{prefix}:UNKNOWN_SYMBOL")
        reduce_only = operation.get("reduce_only") is True
        new_risk = kind in PORTFOLIO_NEW_RISK_ACTIONS and not reduce_only
        new_risk_payload: Mapping[str, Any] = operation
        if kind == "REPLACE_ORDER":
            replacement = operation.get("replacement")
            if not isinstance(replacement, Mapping):
                errors.append(f"{prefix}:REPLACEMENT_OBJECT_REQUIRED")
                replacement = {}
            replacement_allowed = allowed_operation_fields["PLACE_LIMIT"] - {"type"}
            replacement_unknown = sorted(set(replacement) - replacement_allowed)
            if replacement_unknown:
                errors.append(
                    f"{prefix}:UNKNOWN_REPLACEMENT_FIELDS:"
                    + ",".join(str(item) for item in replacement_unknown)
                )
            replacement = {
                key: copy.deepcopy(value)
                for key, value in replacement.items()
                if key in replacement_allowed
            }
            operation["replacement"] = replacement
            new_risk_payload = replacement
            reduce_only = replacement.get("reduce_only") is True
            new_risk = not reduce_only
            replacement_symbol = replacement.get("symbol")
            if replacement_symbol is not None and replacement_symbol not in symbol_analyses:
                errors.append(f"{prefix}:UNKNOWN_REPLACEMENT_SYMBOL")
            symbol = replacement_symbol or symbol
        if new_risk:
            normalized_symbol = str(symbol)
            new_risk_actions_by_symbol[normalized_symbol] = (
                new_risk_actions_by_symbol.get(normalized_symbol, 0) + 1
            )
            hypothesis_id = new_risk_payload.get("hypothesis_id")
            if not isinstance(hypothesis_id, str) or hypothesis_id not in PHI_IDS:
                errors.append(f"{prefix}:REGISTERED_HYPOTHESIS_REQUIRED")
            high_level = selected_by_symbol.get(str(symbol))
            if not isinstance(high_level, Mapping):
                errors.append(f"{prefix}:MATCHING_SYMBOL_DECISION_REQUIRED")
                high_level = {}
            expected_action = (
                {"OPEN_LONG", "ADD_LONG"}
                if new_risk_payload.get("side") == "BUY"
                else {"OPEN_SHORT", "ADD_SHORT"}
                if new_risk_payload.get("side") == "SELL"
                else set()
            )
            if high_level.get("action") not in expected_action:
                errors.append(f"{prefix}:NEW_RISK_CONTRADICTS_SYMBOL_ACTION")
            if high_level.get("selected_phi_id") != hypothesis_id:
                errors.append(f"{prefix}:HYPOTHESIS_NOT_BOUND_TO_SYMBOL_DECISION")
            geometry_id = new_risk_payload.get("geometry_candidate_id")
            if geometry_id != high_level.get("geometry_candidate_id"):
                errors.append(f"{prefix}:GEOMETRY_NOT_BOUND_TO_SYMBOL_DECISION")
            symbol_geometry = {
                item.get("geometry_candidate_id"): item
                for item in _mapping(symbol_analyses.get(str(symbol))).get(
                    "action_geometry_candidates",
                    [],
                )
                if isinstance(item, Mapping)
            }.get(geometry_id)
            if (
                not isinstance(symbol_geometry, Mapping)
                or symbol_geometry.get("status") != "RESEARCH_READY"
            ):
                errors.append(f"{prefix}:RESEARCH_READY_GEOMETRY_REQUIRED")
            high_order = _mapping(high_level.get("order"))
            comparisons = (
                ("notional_usdt", "notional_usdt"),
                ("limit_price", "limit_price"),
                ("stop_price", "stop_loss"),
                ("target_price", "take_profit"),
            )
            for low_field, high_field in comparisons:
                if not _same_finite(
                    new_risk_payload.get(low_field),
                    high_order.get(high_field),
                ):
                    errors.append(
                        f"{prefix}:{low_field.upper()}_NOT_BOUND_TO_SYMBOL_DECISION"
                    )
            high_order_type = str(high_order.get("order_type") or "").upper()
            if kind == "MARKET" and high_order_type != "MARKET":
                errors.append(f"{prefix}:ORDER_TYPE_NOT_BOUND_TO_SYMBOL_DECISION")
            if kind in {"KEEP_ORDER", "REPLACE_ORDER", "PLACE_LIMIT"} and (
                high_order_type != "LIMIT"
            ):
                errors.append(f"{prefix}:ORDER_TYPE_NOT_BOUND_TO_SYMBOL_DECISION")
            probe = new_risk_payload.get("probe")
            if probe not in (None, False, True):
                errors.append(f"{prefix}:PROBE_FLAG_MUST_BE_BOOLEAN")
            if probe is True:
                executed_probe_symbols.add(normalized_symbol)
                activity = _mapping(settings.get("activity_policy"))
                threshold = int(
                    activity.get("valid_hours_without_strategy_fill_before_probe", 6)
                )
                inactivity = _mapping(analysis.get("portfolio_context")).get(
                    "valid_hours_without_strategy_fill"
                )
                if (
                    isinstance(inactivity, bool)
                    or not isinstance(inactivity, int)
                    or inactivity < threshold
                ):
                    errors.append(f"{prefix}:PROBE_INACTIVITY_THRESHOLD_NOT_MET")
                if (
                    high_level.get("active_probe_plan") is not True
                    or high_level.get("market_actionability") != "ACTIONABLE"
                    or high_level.get("execution_intent") != "EXECUTE_NOW"
                ):
                    errors.append(f"{prefix}:ACTIVE_ACTIONABLE_PROBE_PLAN_REQUIRED")
                probe_notional = _finite(new_risk_payload.get("notional_usdt"))
                minimum_probe = (
                    _finite(activity.get("probe_notional_min_usdt")) or 100.0
                )
                maximum_probe = (
                    _finite(activity.get("probe_notional_max_usdt")) or 250.0
                )
                if (
                    probe_notional is None
                    or probe_notional < minimum_probe
                    or probe_notional > maximum_probe
                ):
                    errors.append(f"{prefix}:PROBE_NOTIONAL_OUT_OF_RANGE")
            elif high_level.get("active_probe_plan") is True:
                errors.append(f"{prefix}:DECLARED_PROBE_MUST_SET_PROBE_TRUE")
            authorization = _mapping(new_risk_payload.get("risk_authorization"))
            unknown_authorization = sorted(
                set(authorization) - {"approved", "authority", "reason"}
            )
            if unknown_authorization:
                errors.append(
                    f"{prefix}:UNKNOWN_RISK_AUTHORIZATION_FIELDS:"
                    + ",".join(str(item) for item in unknown_authorization)
                )
            if authorization.get("approved") is not True:
                errors.append(f"{prefix}:EXPLICIT_RISK_AUTHORIZATION_REQUIRED")
            if _finite(new_risk_payload.get("stop_price")) is None:
                errors.append(f"{prefix}:STOP_PRICE_REQUIRED")
            if _finite(new_risk_payload.get("target_price")) is None:
                errors.append(f"{prefix}:TARGET_PRICE_REQUIRED")
        normalized_portfolio_actions.append(operation)

    for index, high_level in enumerate(normalized_symbol_decisions):
        symbol = str(high_level.get("symbol"))
        count = new_risk_actions_by_symbol.get(symbol, 0)
        if high_level.get("action") in NEW_RISK_ACTIONS:
            if high_level.get("execution_intent") == "EXECUTE_NOW" and count != 1:
                errors.append(
                    f"SYMBOL_DECISION_{index}:EXECUTE_NOW_REQUIRES_EXACTLY_ONE_LOW_LEVEL_ACTION"
                )
            if high_level.get("execution_intent") == "PLAN_ONLY" and count != 0:
                errors.append(
                    f"SYMBOL_DECISION_{index}:PLAN_ONLY_FORBIDS_LOW_LEVEL_ACTION"
                )
        elif count:
            errors.append(
                f"SYMBOL_DECISION_{index}:NON_RISK_DECISION_HAS_LOW_LEVEL_NEW_RISK"
            )

    activity = _mapping(settings.get("activity_policy"))
    raw_threshold = activity.get("valid_hours_without_strategy_fill_before_probe", 6)
    if (
        isinstance(raw_threshold, bool)
        or not isinstance(raw_threshold, int)
        or raw_threshold < 1
    ):
        errors.append("ACTIVITY_POLICY_PROBE_THRESHOLD_INVALID")
        threshold = 6
    else:
        threshold = raw_threshold
    inactivity = _mapping(analysis.get("portfolio_context")).get(
        "valid_hours_without_strategy_fill"
    )
    inactivity_known = (
        not isinstance(inactivity, bool)
        and isinstance(inactivity, int)
        and inactivity >= 0
    )
    probe_due = bool(inactivity_known and inactivity >= threshold)
    actionable_symbols = sorted(
        str(item.get("symbol"))
        for item in normalized_symbol_decisions
        if item.get("market_actionability") == "ACTIONABLE"
    )
    typed_veto_symbols = sorted(
        str(item.get("symbol"))
        for item in normalized_symbol_decisions
        if item.get("market_actionability")
        in {"DATA_INVALID", "RISK_VETO", "NOT_ACTIONABLE"}
    )
    executed_new_risk_symbols = sorted(
        symbol for symbol, count in new_risk_actions_by_symbol.items() if count > 0
    )
    if not inactivity_known:
        gate_status = "INACTIVITY_UNKNOWN_NO_HARD_GATE"
        gate_satisfied = True
    elif not probe_due:
        gate_status = "NOT_DUE"
        gate_satisfied = True
    elif executed_new_risk_symbols:
        gate_status = "SATISFIED_BY_EXECUTED_NEW_RISK"
        gate_satisfied = True
    elif not actionable_symbols and typed_veto_symbols:
        gate_status = "SATISFIED_BY_TYPED_SAFETY_VETO"
        gate_satisfied = True
    else:
        gate_status = "BLOCKED_ACTIONABLE_INACTIVITY"
        gate_satisfied = False
        errors.append("ACTIVITY_GATE:EXECUTED_RISK_OR_TYPED_SAFETY_VETO_REQUIRED")
    orchestration_gate = {
        "status": gate_status,
        "satisfied": gate_satisfied,
        "inactivity_hours": inactivity if inactivity_known else UNKNOWN,
        "threshold_hours": threshold,
        "probe_due": probe_due,
        "actionable_symbols": actionable_symbols,
        "typed_safety_veto_symbols": typed_veto_symbols,
        "executed_new_risk_symbols": executed_new_risk_symbols,
        "executed_probe_symbols": sorted(executed_probe_symbols),
        "derivation": (
            "FROZEN_INACTIVITY_PLUS_ENUMS_PLUS_VALIDATED_LOW_LEVEL_ACTIONS;"
            "FREE_TEXT_DOES_NOT_SATISFY_GATE"
        ),
    }

    normalized = {
        "schema_version": "theory-paper-agent-decision.normalized.v1",
        "analysis_digest": analysis.get("analysis_digest"),
        "cycle_id": analysis.get("cycle_id"),
        "decision_at": analysis_decision_at,
        "execution_scope": PAPER_ONLY,
        "executive_summary_zh": copy.deepcopy(decision.get("executive_summary_zh")),
        "portfolio_rationale_zh": copy.deepcopy(decision.get("portfolio_rationale_zh")),
        "news_evidence": copy.deepcopy(decision.get("news_evidence")),
        "method_observations": copy.deepcopy(decision.get("method_observations")),
        "agent_identity": copy.deepcopy(dict(_mapping(agent_identity))),
        "active_method_delta": copy.deepcopy(active_method_delta),
        "method_delta_execution": copy.deepcopy(
            decision.get("method_delta_execution", UNKNOWN)
        ),
        "orchestration_gate": copy.deepcopy(orchestration_gate),
        "symbol_decisions": normalized_symbol_decisions,
        "actions": normalized_portfolio_actions,
        "agent_attestation": copy.deepcopy(dict(attestation)),
    }
    normalized["decision_digest"] = digest_json(normalized)
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized_decision": normalized if not errors else None,
        "orchestration_gate": orchestration_gate,
    }


def _contains_numeric_probability(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lower = str(key).lower()
            if ("probability" in lower or lower in {"prob", "weight"}) and _finite(child) is not None:
                return True
            if _contains_numeric_probability(child):
                return True
    elif isinstance(value, list):
        return any(_contains_numeric_probability(child) for child in value)
    return False


def score_theory_integrity(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Score structural theory integrity only; market outcome and PnL are ignored."""

    hard_failures: list[str] = []
    deductions: list[str] = []
    symbols = analysis.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        hard_failures.append("NO_SYMBOL_ANALYSES")
        symbols = []
    if analysis.get("method_status") != EXPERIMENTAL:
        deductions.append("EXPERIMENTAL_STATUS_MISSING")
    if analysis.get("execution_scope") != PAPER_ONLY:
        hard_failures.append("NON_PAPER_EXECUTION_SCOPE")

    category_passes = {
        "measurement_chain": [],
        "multiscale_roles": [],
        "structural_position": [],
        "phi_competition": [],
        "actor_boundary": [],
        "geometry_boundary": [],
    }
    expected_roles = list(TIMEFRAME_ROLES)
    for symbol_index, raw_symbol in enumerate(symbols):
        symbol = _mapping(raw_symbol)
        label = str(symbol.get("symbol", symbol_index))
        measurement = _mapping(symbol.get("measurement_snapshot"))
        axes = _mapping(measurement.get("axes"))
        measurement_shape_ok = set(axes) == {"D", "L", "C", "F", "R", "K"} and all(
            _mapping(axes.get(axis)).get("status") in {"OBSERVED", "PARTIAL", UNKNOWN}
            for axis in ("D", "L", "C", "F", "R", "K")
        )
        known_axis_fraction = (
            sum(
                _mapping(axes.get(axis)).get("status") != UNKNOWN
                for axis in ("D", "L", "C", "F", "R", "K")
            )
            / 6.0
            if measurement_shape_ok
            else 0.0
        )
        quality = _mapping(measurement.get("data_quality"))
        coverage = _finite(quality.get("coverage_ratio"))
        coverage_factor = 0.0 if coverage is None else min(1.0, max(0.0, coverage))
        measurement_fraction = known_axis_fraction * coverage_factor
        category_passes["measurement_chain"].append(measurement_fraction)
        if not measurement_shape_ok:
            deductions.append(f"{label}:MEASUREMENT_CHAIN_INCOMPLETE")
        elif measurement_fraction < 0.999:
            deductions.append(f"{label}:MEASUREMENT_OR_SOURCE_COVERAGE_PARTIAL")

        state = _mapping(symbol.get("multi_scale_state_belief"))
        role_states = state.get("role_states")
        role_pairs = (
            [(item.get("timeframe"), item.get("role")) for item in role_states if isinstance(item, Mapping)]
            if isinstance(role_states, list)
            else []
        )
        roles_shape_ok = role_pairs == expected_roles and state.get("aggregation_rule") == (
            "NO_TIMEFRAME_VOTING_LOWER_ROLE_CANNOT_OVERRIDE_PARENT_ROLE"
        )
        known_role_fraction = (
            sum(
                item.get("state_status") != UNKNOWN
                for item in role_states
                if isinstance(item, Mapping)
            )
            / len(expected_roles)
            if roles_shape_ok
            else 0.0
        )
        category_passes["multiscale_roles"].append(known_role_fraction)
        if not roles_shape_ok:
            deductions.append(f"{label}:MULTISCALE_ROLE_DRIFT")
        elif known_role_fraction < 0.999:
            deductions.append(f"{label}:MULTISCALE_STATE_PARTIAL")

        structural = _mapping(symbol.get("structural_position"))
        structural_shape_ok = all(
            key in structural
            for key in (
                "reference_price",
                "operational_phase",
                "nearest_registered_support",
                "nearest_registered_resistance",
                "location_stage",
            )
        )
        structural_known_fraction = (
            sum(
                _known(structural.get(key))
                for key in ("reference_price", "operational_phase", "location_stage")
            )
            / 3.0
            if structural_shape_ok
            else 0.0
        )
        category_passes["structural_position"].append(structural_known_fraction)
        if not structural_shape_ok:
            deductions.append(f"{label}:STRUCTURAL_POSITION_INCOMPLETE")
        elif structural_known_fraction < 0.999:
            deductions.append(f"{label}:STRUCTURAL_POSITION_PARTIAL")

        competition = _mapping(symbol.get("phi_competition"))
        hypotheses = competition.get("hypotheses")
        hypothesis_ids = (
            [item.get("phi_id") for item in hypotheses if isinstance(item, Mapping)]
            if isinstance(hypotheses, list)
            else []
        )
        phi_ok = (
            hypothesis_ids == list(PHI_IDS)
            and competition.get("competition_mode") == "QUALITATIVE_ORDINAL_NON_NORMALIZED"
            and competition.get("single_top_path") == "UNKNOWN_NO_CALIBRATED_COMPETITION_SET"
        )
        if _contains_numeric_probability(competition):
            hard_failures.append(f"{label}:ORDINAL_TREATED_AS_PROBABILITY")
            phi_ok = False
        for hypothesis in hypotheses if isinstance(hypotheses, list) else []:
            if not isinstance(hypothesis, Mapping):
                phi_ok = False
                continue
            if hypothesis.get("is_probability") is not False:
                hard_failures.append(f"{label}:PHI_PROBABILITY_FLAG_INVALID")
            if not hypothesis.get("hard_falsifiers") or not hypothesis.get(
                "next_observable_support"
            ):
                phi_ok = False
        if "PHI_OTHER_UNKNOWN" not in hypothesis_ids:
            hard_failures.append(f"{label}:OTHER_UNKNOWN_MISSING")
        category_passes["phi_competition"].append(phi_ok)
        if not phi_ok:
            deductions.append(f"{label}:PHI_COMPETITION_INVALID")

        actors = _mapping(symbol.get("actor_behavior_hypotheses"))
        actor_ok = "NO PERSON, INSTITUTION, WHALE" in str(
            actors.get("epistemic_boundary", "")
        )
        actor_items = actors.get("items")
        if not isinstance(actor_items, list):
            actor_ok = False
        else:
            for actor in actor_items:
                if not isinstance(actor, Mapping) or actor.get("identity_status") != "NOT_IDENTIFIED":
                    actor_ok = False
                    hard_failures.append(f"{label}:ACTOR_IDENTITY_OVERREACH")
        category_passes["actor_boundary"].append(actor_ok)
        if not actor_ok:
            deductions.append(f"{label}:ACTOR_BOUNDARY_INVALID")

        candidates = symbol.get("action_geometry_candidates")
        geometry_ok = isinstance(candidates, list) and bool(candidates)
        for candidate in candidates if isinstance(candidates, list) else []:
            if not isinstance(candidate, Mapping):
                geometry_ok = False
                continue
            if (
                candidate.get("permission")
                != "REQUIRES_SEPARATE_PORTFOLIO_AND_RISK_GATE"
                or candidate.get("execution_scope") != PAPER_ONLY
                or candidate.get("is_order") is not False
            ):
                geometry_ok = False
                hard_failures.append(f"{label}:GEOMETRY_SELF_AUTHORIZED")
            if candidate.get("status") == "RESEARCH_READY" and (
                _finite(candidate.get("stop_loss")) is None
                or _finite(candidate.get("take_profit")) is None
            ):
                geometry_ok = False
                hard_failures.append(f"{label}:READY_GEOMETRY_UNBOUNDED")
        category_passes["geometry_boundary"].append(geometry_ok)
        if not geometry_ok:
            deductions.append(f"{label}:GEOMETRY_BOUNDARY_INVALID")

    weights = {
        "measurement_chain": 20,
        "multiscale_roles": 15,
        "structural_position": 10,
        "phi_competition": 25,
        "actor_boundary": 15,
        "geometry_boundary": 15,
    }
    uncapped = 0.0
    category_scores: dict[str, int] = {}
    for category, weight in weights.items():
        values = category_passes[category]
        points = weight * (
            sum(float(value) for value in values) / len(values)
            if values
            else 0
        )
        category_scores[category] = round(points)
        uncapped += points
    score = round(uncapped)
    if hard_failures:
        score = min(score, 49)
    return {
        "schema_version": "TheoryIntegrityScore.v1",
        "score": score,
        "uncapped_score": round(uncapped),
        "passing": score >= 80 and not hard_failures,
        "category_scores": category_scores,
        "hard_failures": sorted(set(hard_failures)),
        "deductions": sorted(set(deductions)),
        "pnl_in_score": False,
        "score_boundary": "STRUCTURAL_THEORY_INTEGRITY_ONLY_NOT_PREDICTIVE_VALIDITY",
    }


def _valid_portfolio_risk_action(action: Mapping[str, Any]) -> bool:
    kind = str(action.get("type", action.get("action", ""))).upper()
    payload = _mapping(action.get("replacement")) if kind == "REPLACE_ORDER" else action
    if kind not in PORTFOLIO_NEW_RISK_ACTIONS or payload.get("reduce_only") is True:
        return True
    authorization = _mapping(payload.get("risk_authorization"))
    return (
        isinstance(payload.get("hypothesis_id"), str)
        and payload.get("hypothesis_id") in PHI_IDS
        and _finite(payload.get("stop_price")) is not None
        and _finite(payload.get("target_price")) is not None
        and authorization.get("approved") is True
    )


def score_method_practice(cycle_reviews: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Score observable practice discipline, never profitability."""

    if not isinstance(cycle_reviews, Sequence) or isinstance(cycle_reviews, (str, bytes)):
        cycle_reviews = []
    records = [record for record in cycle_reviews if isinstance(record, Mapping)]
    hard_failures: list[str] = []
    deductions: list[str] = []
    buckets: dict[str, list[bool]] = {
        "evidence_discipline": [],
        "hypothesis_competition": [],
        "falsification_discipline": [],
        "geometry_and_risk": [],
        "review_learning": [],
    }
    actionable_inactive = 0
    active_actions = 0
    for index, record in enumerate(records):
        raw_decision = _mapping(record.get("decision"))
        decision = _mapping(raw_decision.get("validated_decision")) or raw_decision
        review = _mapping(record.get("review"))
        decision_rows = decision.get("symbol_decisions")
        symbol_decisions = (
            [item for item in decision_rows if isinstance(item, Mapping)]
            if isinstance(decision_rows, list)
            else []
        )
        action_rows = decision.get("actions")
        portfolio_actions = (
            [item for item in action_rows if isinstance(item, Mapping)]
            if isinstance(action_rows, list)
            else []
        )
        integrity = _mapping(record.get("analysis")).get("theory_integrity_score")
        integrity_ok = _mapping(integrity).get("passing") is True
        facts_ok = bool(symbol_decisions) and all(
            isinstance(action.get("fact_refs"), list) and bool(action.get("fact_refs"))
            for action in symbol_decisions
        )
        buckets["evidence_discipline"].append(integrity_ok and facts_ok)

        competition_ok = bool(symbol_decisions) and all(
            action.get("selected_phi_id") in PHI_IDS
            and isinstance(action.get("alternative_phi_ids"), list)
            and len(action.get("alternative_phi_ids")) >= 1
            for action in symbol_decisions
        )
        buckets["hypothesis_competition"].append(competition_ok)

        lifecycle_ok = bool(symbol_decisions) and all(
            isinstance(action.get("hard_falsifier"), str)
            and bool(action.get("hard_falsifier", "").strip())
            and isinstance(action.get("expiry_at"), str)
            for action in symbol_decisions
        )
        if review:
            lifecycle_ok = lifecycle_ok and review.get("hypothesis_status") in {
                "SUPPORTED_ACTIVE",
                "SUPPORTED_AT_EXPIRY",
                "FALSIFIED",
                "EXPIRED_UNSUPPORTED",
                "UNRESOLVED_UNKNOWN",
            }
        buckets["falsification_discipline"].append(lifecycle_ok)

        risk_ok = all(
            _valid_portfolio_risk_action(action) for action in portfolio_actions
        )
        buckets["geometry_and_risk"].append(risk_ok)
        if any(
            str(action.get("type", "")).upper() in PORTFOLIO_NEW_RISK_ACTIONS
            and action.get("reduce_only") is not True
            for action in portfolio_actions
        ):
            active_actions += 1
        if symbol_decisions and all(
            action.get("action") in INACTIVE_ACTIONS for action in symbol_decisions
        ):
            if any(
                action.get("market_actionability") == "ACTIONABLE"
                for action in symbol_decisions
            ):
                if not any(
                    action.get("active_probe_plan") is True
                    for action in symbol_decisions
                ):
                    actionable_inactive += 1

        issue_codes = review.get("method_issue_codes")
        learning_ok = (
            isinstance(review.get("evidence_refs"), list)
            and isinstance(issue_codes, list)
            and all(code in ISSUE_TAXONOMY for code in issue_codes)
            and isinstance(review.get("lesson"), str)
            and bool(review.get("lesson", "").strip())
        )
        buckets["review_learning"].append(learning_ok)
        if review.get("posthoc_thesis_changed") is True:
            hard_failures.append(f"RECORD_{index}:POSTHOC_THESIS_REWRITE")
        if decision.get("execution_scope") not in (None, PAPER_ONLY):
            hard_failures.append(f"RECORD_{index}:NON_PAPER_EXECUTION")
        if not risk_ok:
            hard_failures.append(f"RECORD_{index}:UNBOUNDED_NEW_RISK")

    if not records:
        hard_failures.append("NO_PRACTICE_RECORDS")
    if len(records) >= 4 and active_actions == 0 and actionable_inactive >= 4:
        hard_failures.append("UNDERTRADING_WITHOUT_ACTIVE_PROBE_PLAN")
    scores: dict[str, int] = {}
    total = 0
    for category, values in buckets.items():
        points = round(20 * (sum(values) / len(values) if values else 0))
        scores[category] = points
        total += points
        if values and not all(values):
            deductions.append(category.upper() + "_INCOMPLETE")
    uncapped = total
    if hard_failures:
        total = min(total, 49)
    return {
        "schema_version": "MethodPracticeScore.v1",
        "score": total,
        "uncapped_score": uncapped,
        "passing": total >= 80 and not hard_failures,
        "category_scores": scores,
        "hard_failures": sorted(set(hard_failures)),
        "deductions": sorted(set(deductions)),
        "record_count": len(records),
        "pnl_in_score": False,
        "score_boundary": "PROCESS_DISCIPLINE_ONLY_PROFIT_AND_LOSS_EXCLUDED",
    }


def score_cycle(
    analysis: Mapping[str, Any],
    decision: Mapping[str, Any] | None = None,
    review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return both independent scores for a cycle or review window."""

    record = {
        "analysis": analysis,
        "decision": decision or {},
        "review": review or {},
    }
    return {
        "schema_version": "theory-paper-dual-score.v1",
        "theory_integrity": score_theory_integrity(analysis),
        "method_practice": score_method_practice([record]),
        "pnl_in_scores": False,
    }


def build_method_candidates(
    cycle_reviews: Sequence[Mapping[str, Any]],
    review_id: str | None = None,
    window_hours: int = 8,
) -> list[dict[str, Any]]:
    """Generate deterministic, single-axis proposals; never edit theory in place."""

    if isinstance(window_hours, bool) or not isinstance(window_hours, int) or window_hours <= 0:
        raise TheoryPaperError("method candidate window_hours must be a positive integer")
    records = [item for item in cycle_reviews if isinstance(item, Mapping)]
    identifier = review_id or "REVIEW-" + digest_json(records)[:16]
    occurrences: dict[str, list[str]] = {}
    for index, record in enumerate(records):
        review = _mapping(record.get("review"))
        codes = review.get("method_issue_codes")
        if not isinstance(codes, list):
            continue
        evidence_id = str(record.get("cycle_id") or f"RECORD-{index}")
        for code in codes:
            if code in ISSUE_TAXONOMY:
                occurrences.setdefault(code, []).append(evidence_id)
        method_score = _mapping(record.get("method_practice"))
        for deduction in method_score.get("deductions", []):
            mapping = {
                "EVIDENCE_DISCIPLINE_INCOMPLETE": "DATA_QUALITY",
                "HYPOTHESIS_COMPETITION_INCOMPLETE": "PHI_COMPETITION",
                "FALSIFICATION_DISCIPLINE_INCOMPLETE": "FALSIFICATION",
                "GEOMETRY_AND_RISK_INCOMPLETE": "RISK_DISCIPLINE",
                "REVIEW_LEARNING_INCOMPLETE": "POSTHOC_REASONING",
            }
            code = mapping.get(str(deduction))
            if code:
                occurrences.setdefault(code, []).append(evidence_id)
        for failure in method_score.get("hard_failures", []):
            text = str(failure)
            if "POSTHOC" in text:
                occurrences.setdefault("POSTHOC_REASONING", []).append(evidence_id)
            elif "UNDERTRADING" in text:
                occurrences.setdefault("UNDERTRADING", []).append(evidence_id)
            elif "UNBOUNDED_NEW_RISK" in text:
                occurrences.setdefault("RISK_DISCIPLINE", []).append(evidence_id)

    score = score_method_practice(records)
    for failure in score["hard_failures"]:
        if "POSTHOC" in failure:
            occurrences.setdefault("POSTHOC_REASONING", []).append(str(failure))
        elif "UNDERTRADING" in failure:
            occurrences.setdefault("UNDERTRADING", []).append(str(failure))
        elif "UNBOUNDED_NEW_RISK" in failure:
            occurrences.setdefault("RISK_DISCIPLINE", []).append(str(failure))

    candidates: list[dict[str, Any]] = []
    ordered = sorted(occurrences, key=lambda code: (-len(occurrences[code]), code))
    for priority, code in enumerate(ordered, start=1):
        spec = ISSUE_TAXONOMY[code]
        candidate: dict[str, Any] = {
            "schema_version": "MethodCandidate.v1",
            "review_id": identifier,
            "review_window_hours": window_hours,
            "nominal_review_window_hours": 8,
            "priority": priority,
            "issue_code": code,
            "occurrence_count": len(occurrences[code]),
            "evidence_refs": sorted(set(occurrences[code])),
            "change_axis": spec["change_axis"],
            "proposed_method_delta": spec["proposal"],
            "falsification_test": spec["test"],
            "next_evaluation_window": "NEXT_UNSEEN_8H_WINDOW",
            "status": "PROPOSED_NOT_ADOPTED",
            "automatic_core_edit": False,
            "outcome_or_pnl_used_to_score": False,
        }
        candidate["method_candidate_id"] = "MC-" + digest_json(candidate)[:20]
        candidates.append(candidate)
    return candidates
