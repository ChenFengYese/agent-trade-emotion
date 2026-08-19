"""V3.1 successor contracts for native sentiment sources and graph projection.

The module is deliberately pure Domain code.  It registers which public
source semantics may inform each of the twelve sentiment axes, admits only
point-in-time evidence with explicit source, clock, quality and coverage
status, and creates deterministic graph-node/edge projections.  It performs
no IO, estimates no probabilities or expected values, and grants no execution
authority.

An allowed source is not itself a directional sentiment conclusion.  A
non-UNKNOWN ordinal state therefore requires a separately digest-bound axis
state whose evidence ids all resolve to admitted native evidence.  Missing or
unqualified evidence remains UNKNOWN and is never converted to zero.
"""

from __future__ import annotations

from copy import deepcopy
import re
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_digest, self_digest, verify_self_digest
from .market_knowledge_graph import (
    build_graph_node_revision,
    verify_graph_node_revision,
)


class V31SentimentNativeProjectionError(ValueError):
    """A native-source registry or projection violated its frozen contract."""


V31_NATIVE_SENTIMENT_AXES = (
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

_AXIS_INDEX = {axis: index for index, axis in enumerate(V31_NATIVE_SENTIMENT_AXES)}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ROLES = frozenset({"DIRECT", "PROXY", "DERIVED"})
_ADMISSION_STATUSES = frozenset({"ADMITTED", "REJECTED", "UNKNOWN"})
_CLOCK_STATUSES = frozenset({"VALID", "INVALID", "UNKNOWN"})
_QUALITY_STATUSES = frozenset({"HIGH", "MEDIUM", "LOW", "UNUSABLE", "UNKNOWN"})
_COVERAGE_STATUSES = frozenset({"SUFFICIENT", "INSUFFICIENT", "UNKNOWN"})
_OBSERVATION_STATUSES = frozenset({"OBSERVED", "SOURCE_UNAVAILABLE", "UNKNOWN"})
_ADMISSIBLE_QUALITY = frozenset({"HIGH", "MEDIUM"})
_REQUIRED_COHERENCE_TIMEFRAMES = ("15m", "1h", "4h", "1d")
_TIMEFRAME_ORDER = {value: index for index, value in enumerate(_REQUIRED_COHERENCE_TIMEFRAMES)}

_PROHIBITED_KEYS = frozenset(
    {
        "probability",
        "probability_pct",
        "confidence_pct",
        "expected_value",
        "ev",
        "brier",
        "ece",
        "total_sentiment_score",
    }
)


def _source_rule(
    *,
    native_external: bool,
    minimum_input_datum_count: int = 0,
    required_input_metric_kinds: Sequence[str] = (),
    requires_closed_inputs: bool = False,
    required_closed_timeframes: Sequence[str] = (),
    claim_ceiling: str,
    limitation: str,
) -> dict[str, Any]:
    return {
        "native_external": native_external,
        "minimum_input_datum_count": minimum_input_datum_count,
        "required_input_metric_kinds": sorted(required_input_metric_kinds),
        "requires_closed_inputs": requires_closed_inputs,
        "required_closed_timeframes": list(required_closed_timeframes),
        "claim_ceiling": claim_ceiling,
        "limitations": [limitation],
    }


_SOURCE_KIND_RULES: dict[str, dict[str, Any]] = {
    "PUBLIC_MARK_OR_INDEX_PRICE": _source_rule(
        native_external=True,
        claim_ceiling="OBSERVED_PRICE_STATE_ONLY",
        limitation="A price observation is not attention or forced-liquidation evidence.",
    ),
    "PUBLIC_CLOSED_CANDLE_SERIES": _source_rule(
        native_external=True,
        requires_closed_inputs=True,
        claim_ceiling="OBSERVED_CLOSED_CANDLE_PATH_ONLY",
        limitation="Closed candles do not by themselves identify a mechanism.",
    ),
    "PUBLIC_ORDER_BOOK_SNAPSHOT": _source_rule(
        native_external=True,
        claim_ceiling="SINGLE_BOOK_STATE_NOT_RESILIENCE",
        limitation="One order-book snapshot cannot establish liquidity resilience.",
    ),
    "PUBLIC_AGGRESSOR_TRADE_SAMPLE": _source_rule(
        native_external=True,
        claim_ceiling="SAMPLED_ACTIVE_FLOW_ONLY",
        limitation="A bounded trade sample does not establish persistent participation.",
    ),
    "PUBLIC_CLOSED_CANDLE_VOLUME": _source_rule(
        native_external=True,
        requires_closed_inputs=True,
        claim_ceiling="PARTICIPATION_MAGNITUDE_NOT_DIRECTION",
        limitation="Volume alone cannot be assigned a buy or sell direction.",
    ),
    "PUBLIC_FUNDING_RATE": _source_rule(
        native_external=True,
        claim_ceiling="VENUE_FUNDING_OBSERVATION_ONLY",
        limitation="Funding alone is not complete positioning evidence.",
    ),
    "PUBLIC_POSITION_RATIO": _source_rule(
        native_external=True,
        claim_ceiling="PUBLISHED_POSITION_RATIO_ONLY",
        limitation="Published account ratios do not identify position size or hidden books.",
    ),
    "PUBLIC_PERPETUAL_BASIS": _source_rule(
        native_external=True,
        claim_ceiling="BASIS_PROXY_ONLY",
        limitation="Basis mixes funding expectations, liquidity and risk premia.",
    ),
    "PUBLIC_OPEN_INTEREST": _source_rule(
        native_external=True,
        claim_ceiling="OPEN_INTEREST_LEVEL_ONLY",
        limitation="Open interest level has no directional sign by itself.",
    ),
    "PUBLIC_LIQUIDATION_EVENT_FEED": _source_rule(
        native_external=True,
        claim_ceiling="PUBLISHED_LIQUIDATION_EVENTS_ONLY",
        limitation="Venue liquidation coverage may be incomplete across venues.",
    ),
    "PUBLIC_ADL_OR_LIQUIDATION_RISK_INDICATOR": _source_rule(
        native_external=True,
        claim_ceiling="PUBLISHED_RISK_INDICATOR_ONLY",
        limitation="An ADL or risk indicator is not a complete liquidation ledger.",
    ),
    "PUBLIC_ORDER_BOOK_SEQUENCE": _source_rule(
        native_external=True,
        claim_ceiling="OBSERVED_DEPTH_SPREAD_SEQUENCE_ONLY",
        limitation="A sequence supports description, not universal shock resilience.",
    ),
    "PUBLIC_TRADE_IMPACT_RECOVERY_SEQUENCE": _source_rule(
        native_external=True,
        claim_ceiling="OBSERVED_IMPACT_RECOVERY_WINDOW_ONLY",
        limitation="Recovery evidence is limited to the captured impact window.",
    ),
    "PUBLIC_MULTI_SNAPSHOT_DEPTH_SPREAD_HISTORY": _source_rule(
        native_external=True,
        claim_ceiling="MULTI_SNAPSHOT_LIQUIDITY_PROXY_ONLY",
        limitation="Unshocked history is only a proxy for resilience.",
    ),
    "PUBLIC_OPTION_IMPLIED_VOLATILITY": _source_rule(
        native_external=True,
        claim_ceiling="MARKET_IMPLIED_VOLATILITY_NOT_PHYSICAL_PROBABILITY",
        limitation="Option-implied measures include risk premia and market frictions.",
    ),
    "OFFICIAL_INSTITUTIONAL_RELEASE": _source_rule(
        native_external=True,
        claim_ceiling="PUBLISHED_OFFICIAL_CONTENT_ONLY",
        limitation="Published content does not prove hidden intent or market impact.",
    ),
    "OFFICIAL_EXCHANGE_OR_ISSUER_NOTICE": _source_rule(
        native_external=True,
        claim_ceiling="PUBLISHED_OFFICIAL_NOTICE_ONLY",
        limitation="A notice requires a separate reaction window before impact claims.",
    ),
    "VERIFIED_SECONDARY_EVENT_REPORT": _source_rule(
        native_external=True,
        claim_ceiling="VERIFIED_SECONDARY_EVENT_PROXY_ONLY",
        limitation="Secondary reporting cannot silently replace unavailable primary text.",
    ),
    "PUBLIC_PLATFORM_ENGAGEMENT_METRIC": _source_rule(
        native_external=True,
        claim_ceiling="PLATFORM_SPECIFIC_ENGAGEMENT_ONLY",
        limitation="Public engagement is platform-specific and not population sentiment.",
    ),
    "PUBLIC_SEARCH_INTEREST_SERIES": _source_rule(
        native_external=True,
        claim_ceiling="SEARCH_ATTENTION_ONLY",
        limitation="Search interest measures attention, not direction or intent.",
    ),
    "ADMITTED_PUBLIC_CORPUS_MENTION_SERIES": _source_rule(
        native_external=True,
        claim_ceiling="CORPUS_BOUNDED_ATTENTION_PROXY_ONLY",
        limitation="Mention counts require a frozen corpus and cannot be raw headline counts.",
    ),
    "PUBLIC_CROSS_ASSET_CLOSED_MARKET_DATA": _source_rule(
        native_external=True,
        requires_closed_inputs=True,
        claim_ceiling="OBSERVED_CROSS_ASSET_PATH_ONLY",
        limitation="Cross-asset co-movement is not a stable regime or causal relation.",
    ),
    "OFFICIAL_MACROECONOMIC_SERIES": _source_rule(
        native_external=True,
        claim_ceiling="OFFICIAL_MACRO_VINTAGE_ONLY",
        limitation="Macro releases require vintage and publication-time handling.",
    ),
    "CLOSED_CANDLE_DIRECTIONAL_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("CLOSED_CANDLE_RETURN",),
        requires_closed_inputs=True,
        claim_ceiling="DERIVED_DIRECTIONAL_DESCRIPTION_ONLY",
        limitation="The measure is descriptive and not a calibrated forecast.",
    ),
    "CLOSED_CANDLE_STRUCTURE_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=3,
        required_input_metric_kinds=("CLOSED_CANDLE_OHLCV",),
        requires_closed_inputs=True,
        claim_ceiling="DERIVED_STRUCTURE_DESCRIPTION_ONLY",
        limitation="Structure depends on the frozen window and transform.",
    ),
    "RELATIVE_PARTICIPATION_FLOW_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("CLOSED_CANDLE_VOLUME", "PUBLIC_AGGRESSOR_FLOW"),
        claim_ceiling="DERIVED_PARTICIPATION_FLOW_DESCRIPTION_ONLY",
        limitation="Participation magnitude and active-flow direction remain distinct.",
    ),
    "CROWDING_COMPOSITE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("FUNDING_RATE", "POSITION_RATIO_OR_BASIS"),
        claim_ceiling="DERIVED_CROWDING_PROXY_ONLY",
        limitation="The composite cannot reveal unobserved position sizes.",
    ),
    "CROSS_CAPTURE_OPEN_INTEREST_CHANGE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("OPEN_INTEREST_LEVEL",),
        claim_ceiling="DERIVED_OPEN_INTEREST_CHANGE_ONLY",
        limitation="Open-interest change is not directional leverage demand by itself.",
    ),
    "LIQUIDATION_AGGREGATE": _source_rule(
        native_external=False,
        minimum_input_datum_count=1,
        required_input_metric_kinds=("LIQUIDATION_EVENT",),
        claim_ceiling="DERIVED_CAPTURED_LIQUIDATION_AGGREGATE_ONLY",
        limitation="Missing liquidation events remain unknown and are never zero.",
    ),
    "OI_PRICE_VOLUME_DELEVERAGING_COMPOSITE": _source_rule(
        native_external=False,
        minimum_input_datum_count=3,
        required_input_metric_kinds=("OPEN_INTEREST_CHANGE", "PRICE_CHANGE", "ACTIVE_VOLUME"),
        claim_ceiling="FORCED_DELEVERAGING_PROXY_NOT_DIRECT_LIQUIDATION",
        limitation="The composite is only a proxy and price alone is forbidden.",
    ),
    "LIQUIDITY_SHOCK_RECOVERY_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("BOOK_OR_IMPACT_SEQUENCE",),
        claim_ceiling="WINDOW_BOUND_SHOCK_RECOVERY_DESCRIPTION_ONLY",
        limitation="Resilience is limited to the captured sequence and shock definition.",
    ),
    "CLOSED_CANDLE_TAIL_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("CLOSED_CANDLE_OHLCV",),
        requires_closed_inputs=True,
        claim_ceiling="DERIVED_REALIZED_TAIL_DESCRIPTION_ONLY",
        limitation="Realized tail measures do not estimate future tail probability.",
    ),
    "EVENT_WINDOW_MARKET_REACTION": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("INFORMATION_EVENT", "CLOSED_CANDLE_RETURN"),
        claim_ceiling="EVENT_WINDOW_ASSOCIATION_NOT_CAUSAL_EFFECT",
        limitation="A reaction window is not structural causal identification.",
    ),
    "ATTENTION_BASELINE_CHANGE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("ATTENTION_OBSERVATION",),
        claim_ceiling="DERIVED_ATTENTION_CHANGE_NOT_PRICE_DIRECTION",
        limitation="Attention change does not establish bullish or bearish intent.",
    ),
    "CROSS_MARKET_REGIME_MEASURE": _source_rule(
        native_external=False,
        minimum_input_datum_count=2,
        required_input_metric_kinds=("CROSS_ASSET_RETURN",),
        claim_ceiling="DERIVED_WINDOW_SPECIFIC_REGIME_ONLY",
        limitation="A regime label is window- and transform-dependent.",
    ),
    "CLOSED_MULTI_TIMEFRAME_COHERENCE": _source_rule(
        native_external=False,
        minimum_input_datum_count=4,
        required_input_metric_kinds=("CLOSED_CANDLE_RETURN",),
        requires_closed_inputs=True,
        required_closed_timeframes=_REQUIRED_COHERENCE_TIMEFRAMES,
        claim_ceiling="DERIVED_CLOSED_MULTI_TIMEFRAME_RELATION_ONLY",
        limitation="Open candles and single timeframes cannot support coherence.",
    ),
}


_AXIS_SOURCE_POLICY: dict[str, dict[str, tuple[str, ...]]] = {
    "PRICE_DIRECTIONAL_PRESSURE": {
        "direct": ("PUBLIC_MARK_OR_INDEX_PRICE", "PUBLIC_CLOSED_CANDLE_SERIES"),
        "proxy": ("PUBLIC_ORDER_BOOK_SNAPSHOT", "PUBLIC_AGGRESSOR_TRADE_SAMPLE"),
        "derived": ("CLOSED_CANDLE_DIRECTIONAL_MEASURE",),
    },
    "STRUCTURE_PERSISTENCE": {
        "direct": (),
        "proxy": ("PUBLIC_CLOSED_CANDLE_SERIES",),
        "derived": ("CLOSED_CANDLE_STRUCTURE_MEASURE",),
    },
    "PARTICIPATION_AND_ACTIVE_FLOW": {
        "direct": ("PUBLIC_CLOSED_CANDLE_VOLUME", "PUBLIC_AGGRESSOR_TRADE_SAMPLE"),
        "proxy": (),
        "derived": ("RELATIVE_PARTICIPATION_FLOW_MEASURE",),
    },
    "CROWDING_DIRECTION": {
        "direct": ("PUBLIC_FUNDING_RATE", "PUBLIC_POSITION_RATIO"),
        "proxy": ("PUBLIC_PERPETUAL_BASIS", "PUBLIC_OPEN_INTEREST"),
        "derived": ("CROWDING_COMPOSITE",),
    },
    "LEVERAGE_CHANGE": {
        "direct": ("PUBLIC_OPEN_INTEREST",),
        "proxy": ("PUBLIC_FUNDING_RATE", "PUBLIC_PERPETUAL_BASIS"),
        "derived": ("CROSS_CAPTURE_OPEN_INTEREST_CHANGE",),
    },
    "FORCED_DELEVERAGING_PRESSURE": {
        "direct": (
            "PUBLIC_LIQUIDATION_EVENT_FEED",
            "PUBLIC_ADL_OR_LIQUIDATION_RISK_INDICATOR",
        ),
        "proxy": ("OI_PRICE_VOLUME_DELEVERAGING_COMPOSITE",),
        "derived": ("LIQUIDATION_AGGREGATE",),
    },
    "LIQUIDITY_RESILIENCE": {
        "direct": (
            "PUBLIC_ORDER_BOOK_SEQUENCE",
            "PUBLIC_TRADE_IMPACT_RECOVERY_SEQUENCE",
        ),
        "proxy": ("PUBLIC_MULTI_SNAPSHOT_DEPTH_SPREAD_HISTORY",),
        "derived": ("LIQUIDITY_SHOCK_RECOVERY_MEASURE",),
    },
    "VOLATILITY_AND_TAIL_STRESS": {
        "direct": ("PUBLIC_CLOSED_CANDLE_SERIES", "PUBLIC_OPTION_IMPLIED_VOLATILITY"),
        "proxy": (),
        "derived": ("CLOSED_CANDLE_TAIL_MEASURE",),
    },
    "EVENT_AND_NARRATIVE_REACTION": {
        "direct": ("OFFICIAL_INSTITUTIONAL_RELEASE", "OFFICIAL_EXCHANGE_OR_ISSUER_NOTICE"),
        "proxy": ("VERIFIED_SECONDARY_EVENT_REPORT",),
        "derived": ("EVENT_WINDOW_MARKET_REACTION",),
    },
    "ATTENTION_AND_AUDIENCE_RESPONSE": {
        "direct": ("PUBLIC_PLATFORM_ENGAGEMENT_METRIC", "PUBLIC_SEARCH_INTEREST_SERIES"),
        "proxy": ("ADMITTED_PUBLIC_CORPUS_MENTION_SERIES",),
        "derived": ("ATTENTION_BASELINE_CHANGE",),
    },
    "CROSS_MARKET_RISK_APPETITE_AND_REGIME": {
        "direct": ("PUBLIC_CROSS_ASSET_CLOSED_MARKET_DATA", "OFFICIAL_MACROECONOMIC_SERIES"),
        "proxy": (),
        "derived": ("CROSS_MARKET_REGIME_MEASURE",),
    },
    "TIMEFRAME_COHERENCE": {
        "direct": (),
        "proxy": (),
        "derived": ("CLOSED_MULTI_TIMEFRAME_COHERENCE",),
    },
}


_AXIS_FORBIDDEN_PROXY_NOTES = {
    axis: ["MISSING_AS_ZERO", "UNADMITTED_OR_FUTURE_SOURCE"]
    for axis in V31_NATIVE_SENTIMENT_AXES
}
_AXIS_FORBIDDEN_PROXY_NOTES["FORCED_DELEVERAGING_PRESSURE"] += [
    "PRICE_ONLY_MOVE",
    "CANDLE_RETURN_ONLY",
]
_AXIS_FORBIDDEN_PROXY_NOTES["LIQUIDITY_RESILIENCE"] += [
    "SINGLE_ORDER_BOOK_SNAPSHOT",
]
_AXIS_FORBIDDEN_PROXY_NOTES["ATTENTION_AND_AUDIENCE_RESPONSE"] += [
    "PRICE_MOVE",
    "TRADING_VOLUME_OR_ORDER_FLOW",
    "UNFROZEN_HEADLINE_COUNT",
]
_AXIS_FORBIDDEN_PROXY_NOTES["TIMEFRAME_COHERENCE"] += [
    "OPEN_CANDLE",
    "SINGLE_TIMEFRAME_OR_PRICE_SNAPSHOT",
]


_OBSERVATION_FIELDS = frozenset(
    {
        "evidence_id",
        "source_kind",
        "axis_bindings",
        "information_bindings",
        "datum_ref",
        "datum_digest",
        "input_datum_bindings",
        "dependency_group_id",
        "observed_at",
        "available_at",
        "admission_status",
        "clock_status",
        "quality_status",
        "coverage_status",
        "source_observation_status",
        "is_closed",
        "timeframes",
        "limitations",
    }
)
_AXIS_BINDING_FIELDS = frozenset({"axis_id", "evidence_role"})
_INFORMATION_BINDING_FIELDS = frozenset({"information_ref", "information_digest"})
_INPUT_BINDING_FIELDS = frozenset(
    {"datum_ref", "datum_digest", "metric_kind", "timeframe", "is_closed"}
)
_AXIS_STATE_FIELDS = frozenset(
    {
        "axis_id",
        "state_ref",
        "state_digest",
        "state_label",
        "ordinal_value",
        "evidence_ids",
        "observed_at",
        "available_at",
        "limitations",
    }
)
_EDGE_FIELDS = frozenset(
    {
        "schema_version",
        "edge_id",
        "source_node_id",
        "target_node_id",
        "relation",
        "axis_id",
        "evidence_id",
        "evidence_role",
        "dependency_group_ids",
        "claim_ceiling",
        "edge_digest",
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V31SentimentNativeProjectionError(code)
    return value.strip()


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V31SentimentNativeProjectionError(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise V31SentimentNativeProjectionError(code)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V31SentimentNativeProjectionError(code) from exc
    if result.tzinfo is None:
        raise V31SentimentNativeProjectionError(code)
    return result.astimezone(UTC)


def _optional_timestamp(value: Any, code: str) -> datetime | None:
    return None if value is None else _timestamp(value, code)


def _time_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def _enum_or_unknown(value: Any, allowed: frozenset[str], code: str) -> str:
    if value is None:
        return "UNKNOWN"
    if not isinstance(value, str) or value not in allowed:
        raise V31SentimentNativeProjectionError(code)
    return value


def _strings(value: Any, code: str, *, allow_empty: bool = True) -> list[str]:
    if value is None and allow_empty:
        return []
    if not isinstance(value, (list, tuple)):
        raise V31SentimentNativeProjectionError(code)
    result = [_text(item, code) for item in value]
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise V31SentimentNativeProjectionError(code)
    return sorted(result)


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).casefold() in _PROHIBITED_KEYS:
                raise V31SentimentNativeProjectionError(
                    "V31_SENTIMENT_UNCALIBRATED_NUMBER_OR_SCORE_FORBIDDEN"
                )
            _reject_forbidden_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_keys(item)


def build_v31_native_sentiment_source_registry() -> dict[str, Any]:
    """Return the frozen twelve-axis direct/proxy/derived/UNKNOWN matrix."""

    axes = []
    for axis in V31_NATIVE_SENTIMENT_AXES:
        policy = _AXIS_SOURCE_POLICY[axis]
        axes.append(
            {
                "axis_id": axis,
                "direct_source_kinds": sorted(policy["direct"]),
                "proxy_source_kinds": sorted(policy["proxy"]),
                "derived_source_kinds": sorted(policy["derived"]),
                "unknown_source_policy": {
                    "status": "UNKNOWN",
                    "missing_is_zero": False,
                    "required_when": (
                        "NO_SOURCE_PASSES_ADMISSION_CLOCK_QUALITY_COVERAGE_AND_LINEAGE"
                    ),
                },
                "forbidden_proxy_notes": sorted(_AXIS_FORBIDDEN_PROXY_NOTES[axis]),
            }
        )
    document = {
        "schema_id": "theory_paper_v2_v31_native_sentiment_source_registry",
        "schema_version": "2.0.0",
        "axes": axes,
        "source_kind_rules": {
            key: deepcopy(value) for key, value in sorted(_SOURCE_KIND_RULES.items())
        },
        "axis_count": len(axes),
        "public_data_only": True,
        "executable": False,
        "claim_boundaries": [
            "NO_CALIBRATED_PROBABILITY",
            "NO_EXPECTED_VALUE",
            "NO_TRADING_OR_EXECUTION_AUTHORITY",
            "SOURCE_AVAILABILITY_IS_NOT_DIRECTIONAL_SENTIMENT",
        ],
    }
    return self_digest(document, "registry_digest")


def verify_v31_native_sentiment_source_registry(document: Mapping[str, Any]) -> str:
    """Verify the registry is byte-semantic equivalent to the frozen matrix."""

    if not isinstance(document, Mapping):
        raise V31SentimentNativeProjectionError("V31_SENTIMENT_REGISTRY_INVALID")
    try:
        supplied = verify_self_digest(document, "registry_digest")
    except ValueError as exc:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_REGISTRY_DIGEST_INVALID"
        ) from exc
    expected = build_v31_native_sentiment_source_registry()
    if dict(document) != expected:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_REGISTRY_CANONICAL_FORM_INVALID"
        )
    return supplied


def _normalize_axis_bindings(value: Any, *, source_kind: str) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_EVIDENCE_AXIS_BINDINGS_REQUIRED"
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _AXIS_BINDING_FIELDS:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_EVIDENCE_AXIS_BINDING_INVALID"
            )
        axis = str(item.get("axis_id") or "")
        role = str(item.get("evidence_role") or "")
        if axis not in _AXIS_INDEX or role not in _SOURCE_ROLES or axis in seen:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_EVIDENCE_AXIS_BINDING_INVALID"
            )
        policy_key = role.casefold()
        if source_kind not in _AXIS_SOURCE_POLICY[axis][policy_key]:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_SOURCE_KIND_AXIS_ROLE_FORBIDDEN"
            )
        seen.add(axis)
        result.append({"axis_id": axis, "evidence_role": role})
    return sorted(result, key=lambda row: _AXIS_INDEX[row["axis_id"]])


def _normalize_information_bindings(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_INFORMATION_BINDINGS_INVALID"
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _INFORMATION_BINDING_FIELDS:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_INFORMATION_BINDING_INVALID"
            )
        ref = _text(
            item.get("information_ref"), "V31_SENTIMENT_INFORMATION_REF_INVALID"
        )
        if ref in seen:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_INFORMATION_BINDING_DUPLICATE"
            )
        seen.add(ref)
        result.append(
            {
                "information_ref": ref,
                "information_digest": _digest(
                    item.get("information_digest"),
                    "V31_SENTIMENT_INFORMATION_DIGEST_INVALID",
                ),
            }
        )
    return sorted(result, key=lambda row: row["information_ref"])


def _normalize_input_bindings(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_INPUT_DATUM_BINDINGS_INVALID"
        )
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _INPUT_BINDING_FIELDS:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_INPUT_DATUM_BINDING_INVALID"
            )
        ref = _text(item.get("datum_ref"), "V31_SENTIMENT_INPUT_DATUM_REF_INVALID")
        if ref in seen:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_INPUT_DATUM_BINDING_DUPLICATE"
            )
        timeframe = item.get("timeframe")
        if timeframe is not None:
            timeframe = _text(timeframe, "V31_SENTIMENT_INPUT_TIMEFRAME_INVALID")
        is_closed = item.get("is_closed")
        if is_closed is not None and not isinstance(is_closed, bool):
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_INPUT_CLOSED_STATUS_INVALID"
            )
        seen.add(ref)
        result.append(
            {
                "datum_ref": ref,
                "datum_digest": _digest(
                    item.get("datum_digest"),
                    "V31_SENTIMENT_INPUT_DATUM_DIGEST_INVALID",
                ),
                "metric_kind": _text(
                    item.get("metric_kind"),
                    "V31_SENTIMENT_INPUT_METRIC_KIND_INVALID",
                ),
                "timeframe": timeframe,
                "is_closed": is_closed,
            }
        )
    return sorted(result, key=lambda row: row["datum_ref"])


def _normalize_observation(
    candidate: Mapping[str, Any], *, decision_at: datetime
) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or not set(candidate).issubset(
        _OBSERVATION_FIELDS
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_SOURCE_OBSERVATION_SCHEMA_INVALID"
        )
    _reject_forbidden_keys(candidate)
    source_kind = _text(
        candidate.get("source_kind"), "V31_SENTIMENT_SOURCE_KIND_INVALID"
    )
    if source_kind not in _SOURCE_KIND_RULES:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_SOURCE_KIND_UNREGISTERED"
        )
    observed_at = _optional_timestamp(
        candidate.get("observed_at"), "V31_SENTIMENT_SOURCE_OBSERVED_AT_INVALID"
    )
    available_at = _optional_timestamp(
        candidate.get("available_at"), "V31_SENTIMENT_SOURCE_AVAILABLE_AT_INVALID"
    )
    if observed_at is not None and available_at is not None:
        if observed_at > available_at:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_SOURCE_CLOCK_ORDER_INVALID"
            )
    if (observed_at is not None and observed_at > decision_at) or (
        available_at is not None and available_at > decision_at
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_FUTURE_SOURCE_FORBIDDEN"
        )
    datum_ref = candidate.get("datum_ref")
    if datum_ref is not None:
        datum_ref = _text(datum_ref, "V31_SENTIMENT_DATUM_REF_INVALID")
    datum_digest = candidate.get("datum_digest")
    if datum_digest is not None:
        datum_digest = _digest(
            datum_digest, "V31_SENTIMENT_DATUM_DIGEST_INVALID"
        )
    if candidate.get("is_closed") is not None and not isinstance(
        candidate.get("is_closed"), bool
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_CLOSED_STATUS_INVALID"
        )
    return {
        "evidence_id": _text(
            candidate.get("evidence_id"), "V31_SENTIMENT_EVIDENCE_ID_INVALID"
        ),
        "source_kind": source_kind,
        "axis_bindings": _normalize_axis_bindings(
            candidate.get("axis_bindings"), source_kind=source_kind
        ),
        "information_bindings": _normalize_information_bindings(
            candidate.get("information_bindings")
        ),
        "datum_ref": datum_ref,
        "datum_digest": datum_digest,
        "input_datum_bindings": _normalize_input_bindings(
            candidate.get("input_datum_bindings")
        ),
        "dependency_group_id": (
            None
            if candidate.get("dependency_group_id") is None
            else _text(
                candidate.get("dependency_group_id"),
                "V31_SENTIMENT_DEPENDENCY_GROUP_INVALID",
            )
        ),
        "observed_at": _time_text(observed_at),
        "available_at": _time_text(available_at),
        "admission_status": _enum_or_unknown(
            candidate.get("admission_status"),
            _ADMISSION_STATUSES,
            "V31_SENTIMENT_ADMISSION_STATUS_INVALID",
        ),
        "clock_status": _enum_or_unknown(
            candidate.get("clock_status"),
            _CLOCK_STATUSES,
            "V31_SENTIMENT_CLOCK_STATUS_INVALID",
        ),
        "quality_status": _enum_or_unknown(
            candidate.get("quality_status"),
            _QUALITY_STATUSES,
            "V31_SENTIMENT_QUALITY_STATUS_INVALID",
        ),
        "coverage_status": _enum_or_unknown(
            candidate.get("coverage_status"),
            _COVERAGE_STATUSES,
            "V31_SENTIMENT_COVERAGE_STATUS_INVALID",
        ),
        "source_observation_status": _enum_or_unknown(
            candidate.get("source_observation_status"),
            _OBSERVATION_STATUSES,
            "V31_SENTIMENT_OBSERVATION_STATUS_INVALID",
        ),
        "is_closed": candidate.get("is_closed"),
        "timeframes": sorted(
            _strings(
                candidate.get("timeframes"),
                "V31_SENTIMENT_TIMEFRAMES_INVALID",
            ),
            key=lambda item: (_TIMEFRAME_ORDER.get(item, len(_TIMEFRAME_ORDER)), item),
        ),
        "limitations": _strings(
            candidate.get("limitations"), "V31_SENTIMENT_LIMITATIONS_INVALID"
        ),
    }


def _assessment_reasons(observation: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if observation["admission_status"] != "ADMITTED":
        reasons.append(f"ADMISSION_{observation['admission_status']}")
    if (
        observation["clock_status"] != "VALID"
        or observation["observed_at"] is None
        or observation["available_at"] is None
    ):
        reasons.append(
            "CLOCK_UNKNOWN"
            if observation["clock_status"] == "UNKNOWN"
            or observation["observed_at"] is None
            or observation["available_at"] is None
            else "CLOCK_INVALID"
        )
    if observation["quality_status"] not in _ADMISSIBLE_QUALITY:
        reasons.append(f"QUALITY_{observation['quality_status']}")
    if observation["coverage_status"] != "SUFFICIENT":
        reasons.append(f"COVERAGE_{observation['coverage_status']}")
    if observation["source_observation_status"] != "OBSERVED":
        reasons.append(f"SOURCE_{observation['source_observation_status']}")
    if (
        not observation["information_bindings"]
        or observation["datum_ref"] is None
        or observation["datum_digest"] is None
        or observation["dependency_group_id"] is None
    ):
        reasons.append("LINEAGE_BINDING_INCOMPLETE")
    rule = _SOURCE_KIND_RULES[observation["source_kind"]]
    inputs = observation["input_datum_bindings"]
    if len(inputs) < rule["minimum_input_datum_count"]:
        reasons.append("DERIVATION_INPUT_COUNT_INSUFFICIENT")
    metrics = {row["metric_kind"] for row in inputs}
    if not set(rule["required_input_metric_kinds"]).issubset(metrics):
        reasons.append("DERIVATION_REQUIRED_METRICS_MISSING")
    if rule["requires_closed_inputs"] and (
        observation["is_closed"] is not True
        or any(row["is_closed"] is not True for row in inputs)
    ):
        reasons.append("CLOSED_INPUT_PROOF_MISSING")
    required_timeframes = rule["required_closed_timeframes"]
    if required_timeframes:
        input_timeframes = {
            row["timeframe"]
            for row in inputs
            if row["metric_kind"] == "CLOSED_CANDLE_RETURN"
            and row["is_closed"] is True
        }
        if set(required_timeframes) != input_timeframes or set(
            required_timeframes
        ) != set(observation["timeframes"]):
            reasons.append("CLOSED_MULTI_TIMEFRAME_SET_INCOMPLETE")
    return sorted(set(reasons))


def _normalize_axis_state(
    candidate: Mapping[str, Any], *, decision_at: datetime
) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or not set(candidate).issubset(
        _AXIS_STATE_FIELDS
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_SCHEMA_INVALID"
        )
    _reject_forbidden_keys(candidate)
    axis = str(candidate.get("axis_id") or "")
    if axis not in _AXIS_INDEX:
        raise V31SentimentNativeProjectionError("V31_SENTIMENT_AXIS_STATE_AXIS_INVALID")
    state_ref = candidate.get("state_ref")
    state_digest = candidate.get("state_digest")
    if (state_ref is None) != (state_digest is None):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_BINDING_INCOMPLETE"
        )
    if state_ref is not None:
        state_ref = _text(state_ref, "V31_SENTIMENT_AXIS_STATE_REF_INVALID")
        state_digest = _digest(
            state_digest, "V31_SENTIMENT_AXIS_STATE_DIGEST_INVALID"
        )
    observed_at = _optional_timestamp(
        candidate.get("observed_at"), "V31_SENTIMENT_AXIS_STATE_OBSERVED_INVALID"
    )
    available_at = _optional_timestamp(
        candidate.get("available_at"), "V31_SENTIMENT_AXIS_STATE_AVAILABLE_INVALID"
    )
    if observed_at is not None and available_at is not None:
        if observed_at > available_at or available_at > decision_at:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_AXIS_STATE_NOT_POINT_IN_TIME"
            )
    if (observed_at is not None and observed_at > decision_at) or (
        available_at is not None and available_at > decision_at
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_NOT_POINT_IN_TIME"
        )
    ordinal = candidate.get("ordinal_value")
    if ordinal is not None and (
        isinstance(ordinal, bool) or not isinstance(ordinal, int) or not -2 <= ordinal <= 2
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_ORDINAL_INVALID"
        )
    state_label = (
        "UNKNOWN_NOT_COMPUTED"
        if candidate.get("state_label") is None
        else _text(
            candidate.get("state_label"), "V31_SENTIMENT_AXIS_STATE_LABEL_INVALID"
        )
    )
    if ordinal is None and not state_label.startswith("UNKNOWN"):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_UNKNOWN_LABEL_REQUIRED"
        )
    if ordinal is not None and state_label.startswith("UNKNOWN"):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_ORDINAL_LABEL_CONFLICT"
        )
    if state_ref is not None and (observed_at is None or available_at is None):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_CLOCK_BINDING_REQUIRED"
        )
    return {
        "axis_id": axis,
        "state_ref": state_ref,
        "state_digest": state_digest,
        "state_label": state_label,
        "ordinal_value": ordinal,
        "evidence_ids": _strings(
            candidate.get("evidence_ids"),
            "V31_SENTIMENT_AXIS_STATE_EVIDENCE_INVALID",
        ),
        "observed_at": _time_text(observed_at),
        "available_at": _time_text(available_at),
        "limitations": _strings(
            candidate.get("limitations"),
            "V31_SENTIMENT_AXIS_STATE_LIMITATIONS_INVALID",
        ),
    }


def _node_identity(prefix: str, reference: str) -> str:
    return f"v31-native-sentiment:{prefix}:{canonical_digest(reference)[:24]}"


def _build_edge(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, Mapping) or set(candidate) not in {
        _EDGE_FIELDS,
        _EDGE_FIELDS - {"edge_digest"},
    }:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_EDGE_SCHEMA_INVALID"
        )
    axis_id = candidate.get("axis_id")
    if axis_id is not None and axis_id not in _AXIS_INDEX:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_EDGE_AXIS_INVALID"
        )
    role = str(candidate.get("evidence_role") or "")
    if role not in _SOURCE_ROLES | {"SOURCE_LINEAGE"}:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_EDGE_ROLE_INVALID"
        )
    normalized = {
        "schema_version": "V3_1_NATIVE_SENTIMENT_GRAPH_EDGE_V2",
        "edge_id": _text(
            candidate.get("edge_id"), "V31_SENTIMENT_GRAPH_EDGE_ID_INVALID"
        ),
        "source_node_id": _text(
            candidate.get("source_node_id"),
            "V31_SENTIMENT_GRAPH_EDGE_SOURCE_INVALID",
        ),
        "target_node_id": _text(
            candidate.get("target_node_id"),
            "V31_SENTIMENT_GRAPH_EDGE_TARGET_INVALID",
        ),
        "relation": _text(
            candidate.get("relation"), "V31_SENTIMENT_GRAPH_EDGE_RELATION_INVALID"
        ),
        "axis_id": axis_id,
        "evidence_id": _text(
            candidate.get("evidence_id"),
            "V31_SENTIMENT_GRAPH_EDGE_EVIDENCE_INVALID",
        ),
        "evidence_role": role,
        "dependency_group_ids": _strings(
            candidate.get("dependency_group_ids"),
            "V31_SENTIMENT_GRAPH_EDGE_DEPENDENCIES_INVALID",
            allow_empty=False,
        ),
        "claim_ceiling": _text(
            candidate.get("claim_ceiling"),
            "V31_SENTIMENT_GRAPH_EDGE_CLAIM_CEILING_INVALID",
        ),
    }
    result = self_digest(normalized, "edge_digest")
    supplied = candidate.get("edge_digest")
    if supplied is not None and supplied != result["edge_digest"]:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_EDGE_DIGEST_MISMATCH"
        )
    return result


def _graph_node(
    *,
    node_id: str,
    node_type: str,
    label: str,
    description: str,
    payload_ref: str,
    payload_digest: str,
    observed_at: str,
    available_at: str,
    dependency_groups: Sequence[str],
    provenance: Sequence[Mapping[str, Any]],
    limitations: Sequence[str],
) -> dict[str, Any]:
    return build_graph_node_revision(
        {
            "schema_version": "V3_1_GRAPH_NODE_REVISION",
            "node_id": node_id,
            "revision": 1,
            "predecessor_digest": None,
            "node_type": node_type,
            "label": label,
            "description": description,
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "observed_at": observed_at,
            "available_at": available_at,
            "validity": {"valid_from": observed_at, "valid_until": None},
            "status": "ACTIVE",
            "dependency_group_ids": sorted(set(dependency_groups)),
            "provenance": list(provenance),
            "created_at": available_at,
            "limitations": sorted(set(limitations)),
        },
        decision_at=available_at,
    )


def build_v31_native_sentiment_projection(
    *,
    projection_id: str,
    instrument_id: str,
    decision_at: str,
    source_observations: Sequence[Mapping[str, Any]],
    axis_state_bindings: Sequence[Mapping[str, Any]] = (),
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit source evidence and project all twelve axes into typed graph state."""

    registry_document = (
        build_v31_native_sentiment_source_registry()
        if registry is None
        else dict(registry)
    )
    registry_digest = verify_v31_native_sentiment_source_registry(registry_document)
    cutoff = _timestamp(decision_at, "V31_SENTIMENT_PROJECTION_DECISION_AT_INVALID")
    projection_identity = _text(
        projection_id, "V31_SENTIMENT_PROJECTION_ID_INVALID"
    )
    instrument = _text(instrument_id, "V31_SENTIMENT_INSTRUMENT_ID_INVALID")
    if isinstance(source_observations, (str, bytes)) or not isinstance(
        source_observations, Sequence
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_SOURCE_OBSERVATIONS_INVALID"
        )
    observations = [
        _normalize_observation(row, decision_at=cutoff) for row in source_observations
    ]
    observations.sort(key=lambda row: row["evidence_id"])
    evidence_ids = [row["evidence_id"] for row in observations]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_EVIDENCE_ID_DUPLICATE"
        )
    bound_datums = [row["datum_ref"] for row in observations if row["datum_ref"]]
    if len(bound_datums) != len(set(bound_datums)):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_DUPLICATE_DATUM_EVIDENCE_FORBIDDEN"
        )

    assessments: list[dict[str, Any]] = []
    eligible_by_axis: dict[str, list[tuple[dict[str, Any], str]]] = {
        axis: [] for axis in V31_NATIVE_SENTIMENT_AXES
    }
    for observation in observations:
        reasons = _assessment_reasons(observation)
        eligible = not reasons
        for binding in observation["axis_bindings"]:
            assessment = self_digest(
                {
                    "schema_version": "V3_1_NATIVE_SENTIMENT_SOURCE_ASSESSMENT_V2",
                    "evidence_id": observation["evidence_id"],
                    "axis_id": binding["axis_id"],
                    "evidence_role": binding["evidence_role"],
                    "source_kind": observation["source_kind"],
                    "eligible": eligible,
                    "reasons": reasons,
                    "claim_ceiling": _SOURCE_KIND_RULES[observation["source_kind"]][
                        "claim_ceiling"
                    ],
                    "missing_is_zero": False,
                },
                "assessment_digest",
            )
            assessments.append(assessment)
            if eligible:
                eligible_by_axis[binding["axis_id"]].append(
                    (observation, binding["evidence_role"])
                )
    assessments.sort(key=lambda row: (_AXIS_INDEX[row["axis_id"]], row["evidence_id"]))

    if isinstance(axis_state_bindings, (str, bytes)) or not isinstance(
        axis_state_bindings, Sequence
    ):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_BINDINGS_INVALID"
        )
    normalized_states = [
        _normalize_axis_state(row, decision_at=cutoff) for row in axis_state_bindings
    ]
    normalized_states.sort(key=lambda row: _AXIS_INDEX[row["axis_id"]])
    if len({row["axis_id"] for row in normalized_states}) != len(normalized_states):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_AXIS_STATE_DUPLICATE"
        )
    supplied_states = {row["axis_id"]: row for row in normalized_states}
    observation_by_id = {row["evidence_id"]: row for row in observations}

    axis_projections: list[dict[str, Any]] = []
    for axis in V31_NATIVE_SENTIMENT_AXES:
        eligible_rows = eligible_by_axis[axis]
        eligible_ids = sorted(row[0]["evidence_id"] for row in eligible_rows)
        supplied = supplied_states.get(axis)
        if supplied is None:
            supplied = {
                "axis_id": axis,
                "state_ref": None,
                "state_digest": None,
                "state_label": "UNKNOWN_NOT_COMPUTED",
                "ordinal_value": None,
                "evidence_ids": [],
                "observed_at": None,
                "available_at": None,
                "limitations": [],
            }
        referenced = supplied["evidence_ids"]
        if any(
            evidence_id not in observation_by_id
            or axis
            not in {
                binding["axis_id"]
                for binding in observation_by_id[evidence_id]["axis_bindings"]
            }
            for evidence_id in referenced
        ):
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_AXIS_STATE_EVIDENCE_NOT_BOUND_TO_AXIS"
            )
        if supplied["ordinal_value"] is not None:
            if (
                not supplied["state_ref"]
                or supplied["observed_at"] is None
                or supplied["available_at"] is None
                or not referenced
                or not set(referenced).issubset(eligible_ids)
            ):
                raise V31SentimentNativeProjectionError(
                    "V31_SENTIMENT_NON_UNKNOWN_STATE_WITHOUT_ADMITTED_EVIDENCE"
                )
        assessment_reasons = sorted(
            {
                reason
                for assessment in assessments
                if assessment["axis_id"] == axis and not assessment["eligible"]
                for reason in assessment["reasons"]
            }
        )
        if supplied["ordinal_value"] is None:
            unknown_reasons = assessment_reasons or [
                (
                    "AXIS_STATE_NOT_COMPUTED_OR_ADMITTED"
                    if eligible_ids
                    else "NO_QUALIFIED_NATIVE_SOURCE"
                )
            ]
        else:
            unknown_reasons = []
        roles = {
            role: sorted(
                row[0]["evidence_id"] for row in eligible_rows if row[1] == role
            )
            for role in ("DIRECT", "PROXY", "DERIVED")
        }
        axis_projections.append(
            self_digest(
                {
                    "schema_version": "V3_1_NATIVE_SENTIMENT_AXIS_PROJECTION_V2",
                    "axis_id": axis,
                    "source_evidence_status": (
                        "AVAILABLE" if eligible_ids else "UNKNOWN"
                    ),
                    "admitted_direct_evidence_ids": roles["DIRECT"],
                    "admitted_proxy_evidence_ids": roles["PROXY"],
                    "admitted_derived_evidence_ids": roles["DERIVED"],
                    "state_ref": supplied["state_ref"],
                    "state_digest": supplied["state_digest"],
                    "state_label": supplied["state_label"],
                    "ordinal_value": supplied["ordinal_value"],
                    "state_evidence_ids": referenced,
                    "state_observed_at": supplied["observed_at"],
                    "state_available_at": supplied["available_at"],
                    "unknown_reasons": unknown_reasons,
                    "missing_is_zero": False,
                    "claim_ceiling": "ORDINAL_AXIS_STATE_NOT_PROBABILITY_OR_ACTION",
                    "limitations": sorted(
                        set(
                            supplied["limitations"]
                            + [
                                "Source availability alone does not determine axis direction.",
                                "The axis grants no trading or execution authority.",
                            ]
                        )
                    ),
                },
                "axis_projection_digest",
            )
        )

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    for observation in observations:
        reasons = _assessment_reasons(observation)
        if reasons:
            continue
        rule = _SOURCE_KIND_RULES[observation["source_kind"]]
        observed_at = observation["observed_at"]
        available_at = observation["available_at"]
        dependency = observation["dependency_group_id"]
        data_node_id = _node_identity("data", observation["datum_ref"])
        provenance = [
            {
                "source_ref": binding["information_ref"],
                "source_digest": binding["information_digest"],
                "observed_at": observed_at,
                "available_at": available_at,
                "revision_ref": f"{binding['information_ref']}@captured",
            }
            for binding in observation["information_bindings"]
        ]
        data_node = _graph_node(
            node_id=data_node_id,
            node_type=("MARKET_FACT" if rule["native_external"] else "DERIVED_MEASURE"),
            label=f"Native sentiment datum {observation['evidence_id']}",
            description=(
                "Point-in-time datum admitted by the V3.1 native sentiment "
                "source registry."
            ),
            payload_ref=observation["datum_ref"],
            payload_digest=observation["datum_digest"],
            observed_at=observed_at,
            available_at=available_at,
            dependency_groups=(dependency,),
            provenance=provenance,
            limitations=observation["limitations"] + rule["limitations"],
        )
        nodes[data_node_id] = data_node
        for information in observation["information_bindings"]:
            info_node_id = _node_identity("information", information["information_ref"])
            info_node = _graph_node(
                node_id=info_node_id,
                node_type="SOURCE_ARTIFACT",
                label=f"Native public source {information['information_ref']}",
                description="Public source artifact admitted for sentiment research only.",
                payload_ref=information["information_ref"],
                payload_digest=information["information_digest"],
                observed_at=observed_at,
                available_at=available_at,
                dependency_groups=(dependency,),
                provenance=(
                    {
                        "source_ref": information["information_ref"],
                        "source_digest": information["information_digest"],
                        "observed_at": observed_at,
                        "available_at": available_at,
                        "revision_ref": f"{information['information_ref']}@captured",
                    },
                ),
                limitations=observation["limitations"] + rule["limitations"],
            )
            prior = nodes.get(info_node_id)
            if prior is not None and prior != info_node:
                raise V31SentimentNativeProjectionError(
                    "V31_SENTIMENT_SHARED_INFORMATION_BINDING_CONFLICT"
                )
            nodes[info_node_id] = info_node
            edge_seed = {
                "source": info_node_id,
                "target": data_node_id,
                "evidence": observation["evidence_id"],
                "relation": "MATERIALIZES_AS_POINT_IN_TIME_DATUM",
            }
            edge_id = f"v31-native-sentiment:edge:{canonical_digest(edge_seed)[:24]}"
            edges[edge_id] = _build_edge(
                {
                    "schema_version": "V3_1_NATIVE_SENTIMENT_GRAPH_EDGE_V2",
                    "edge_id": edge_id,
                    "source_node_id": info_node_id,
                    "target_node_id": data_node_id,
                    "relation": "MATERIALIZES_AS_POINT_IN_TIME_DATUM",
                    "axis_id": None,
                    "evidence_id": observation["evidence_id"],
                    "evidence_role": "SOURCE_LINEAGE",
                    "dependency_group_ids": [dependency],
                    "claim_ceiling": rule["claim_ceiling"],
                }
            )

    projection_by_axis = {row["axis_id"]: row for row in axis_projections}
    for axis in V31_NATIVE_SENTIMENT_AXES:
        axis_projection = projection_by_axis[axis]
        supplied = supplied_states.get(axis)
        axis_observed = (
            supplied["observed_at"]
            if supplied is not None and supplied["observed_at"] is not None
            else _time_text(cutoff)
        )
        axis_available = (
            supplied["available_at"]
            if supplied is not None and supplied["available_at"] is not None
            else _time_text(cutoff)
        )
        eligible_rows = eligible_by_axis[axis]
        dependency_groups = [f"sentiment-axis:{axis}"] + [
            row[0]["dependency_group_id"] for row in eligible_rows
        ]
        if supplied is not None and supplied["state_ref"] is not None:
            payload_ref = supplied["state_ref"]
            payload_digest = supplied["state_digest"]
            provenance = [
                {
                    "source_ref": supplied["state_ref"],
                    "source_digest": supplied["state_digest"],
                    "observed_at": axis_observed,
                    "available_at": axis_available,
                    "revision_ref": f"{supplied['state_ref']}@bound",
                }
            ]
        else:
            payload_ref = f"{projection_identity}:axis:{axis}"
            payload_digest = axis_projection["axis_projection_digest"]
            provenance = [
                {
                    "source_ref": "v31-native-sentiment-source-registry",
                    "source_digest": registry_digest,
                    "observed_at": _time_text(cutoff),
                    "available_at": _time_text(cutoff),
                    "revision_ref": "v31-native-sentiment-source-registry@2.0.0",
                }
            ]
        axis_node_id = _node_identity("axis", f"{instrument}:{axis}")
        nodes[axis_node_id] = _graph_node(
            node_id=axis_node_id,
            node_type="LATENT_STATE",
            label=f"V3.1 sentiment axis {axis}",
            description="Digest-bound ordinal axis state or explicit UNKNOWN.",
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            observed_at=axis_observed,
            available_at=axis_available,
            dependency_groups=dependency_groups,
            provenance=provenance,
            limitations=axis_projection["limitations"],
        )
        for observation, role in eligible_rows:
            data_node_id = _node_identity("data", observation["datum_ref"])
            rule = _SOURCE_KIND_RULES[observation["source_kind"]]
            edge_seed = {
                "source": data_node_id,
                "target": axis_node_id,
                "evidence": observation["evidence_id"],
                "axis": axis,
                "relation": "INFORMS_ORDINAL_SENTIMENT_AXIS",
            }
            edge_id = f"v31-native-sentiment:edge:{canonical_digest(edge_seed)[:24]}"
            edges[edge_id] = _build_edge(
                {
                    "schema_version": "V3_1_NATIVE_SENTIMENT_GRAPH_EDGE_V2",
                    "edge_id": edge_id,
                    "source_node_id": data_node_id,
                    "target_node_id": axis_node_id,
                    "relation": "INFORMS_ORDINAL_SENTIMENT_AXIS",
                    "axis_id": axis,
                    "evidence_id": observation["evidence_id"],
                    "evidence_role": role,
                    "dependency_group_ids": [observation["dependency_group_id"]],
                    "claim_ceiling": rule["claim_ceiling"],
                }
            )

    graph_projection = self_digest(
        {
            "schema_version": "V3_1_NATIVE_SENTIMENT_GRAPH_PROJECTION_V2",
            "nodes": [nodes[key] for key in sorted(nodes)],
            "edges": [edges[key] for key in sorted(edges)],
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
        "graph_projection_digest",
    )
    result = {
        "schema_id": "theory_paper_v2_v31_native_sentiment_projection",
        "schema_version": "2.0.0",
        "projection_id": projection_identity,
        "instrument_id": instrument,
        "decision_at": _time_text(cutoff),
        "registry_digest": registry_digest,
        "source_observations": observations,
        "source_assessments": assessments,
        "axis_state_bindings": normalized_states,
        "axis_projections": axis_projections,
        "graph_projection": graph_projection,
        "public_data_only": True,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "claim_boundaries": [
            "NO_CALIBRATED_PROBABILITY",
            "NO_EXPECTED_VALUE",
            "NO_CAUSAL_EFFECT_FROM_PROJECTION",
            "NO_TRADING_OR_EXECUTION_AUTHORITY",
        ],
    }
    return self_digest(result, "projection_digest")


def verify_v31_native_sentiment_projection(
    document: Mapping[str, Any], *, registry: Mapping[str, Any] | None = None
) -> str:
    """Replay the complete projection and verify every nested digest."""

    if not isinstance(document, Mapping):
        raise V31SentimentNativeProjectionError("V31_SENTIMENT_PROJECTION_INVALID")
    try:
        supplied = verify_self_digest(document, "projection_digest")
    except ValueError as exc:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_PROJECTION_DIGEST_INVALID"
        ) from exc
    rebuilt = build_v31_native_sentiment_projection(
        projection_id=document.get("projection_id"),
        instrument_id=document.get("instrument_id"),
        decision_at=document.get("decision_at"),
        source_observations=document.get("source_observations"),
        axis_state_bindings=document.get("axis_state_bindings"),
        registry=registry,
    )
    if dict(document) != rebuilt:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_PROJECTION_CANONICAL_FORM_INVALID"
        )
    graph = document.get("graph_projection")
    if not isinstance(graph, Mapping):
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_PROJECTION_INVALID"
        )
    try:
        verify_self_digest(graph, "graph_projection_digest")
    except ValueError as exc:
        raise V31SentimentNativeProjectionError(
            "V31_SENTIMENT_GRAPH_PROJECTION_DIGEST_INVALID"
        ) from exc
    for node in graph["nodes"]:
        verify_graph_node_revision(node, decision_at=node["available_at"])
    for edge in graph["edges"]:
        if _build_edge(edge) != edge:
            raise V31SentimentNativeProjectionError(
                "V31_SENTIMENT_GRAPH_EDGE_CANONICAL_FORM_INVALID"
            )
    return supplied
