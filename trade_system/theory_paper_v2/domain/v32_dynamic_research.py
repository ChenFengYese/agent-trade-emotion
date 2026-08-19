"""Pure V3.2 dynamic-research state contracts.

This module separates epistemic unknowns from action effects, promotes
reflexive liquidity zones and market regimes to typed state, and allows only
three Agent-assigned subjective plausibility tiers.  It owns
no files, clocks, network, Agent transport, portfolio mutation, or execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)


class V32DynamicResearchError(ValueError):
    """A V3.2 dynamic-research invariant failed closed."""


SCHEMA_ID = "theory_paper_v32_dynamic_research_state_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "dynamic_research_state_digest"

UNKNOWN_TYPES = (
    "UNKNOWN_FACT_INTEGRITY",
    "UNKNOWN_PERMISSION",
    "UNKNOWN_MAX_LOSS",
    "UNKNOWN_DIRECTION",
    "UNKNOWN_CAUSE",
    "UNKNOWN_ACTOR",
    "UNKNOWN_NARRATIVE_ADOPTION",
    "UNKNOWN_FUTURE",
    "UNKNOWN_OUTCOME",
)
UNKNOWN_BEHAVIOR_EFFECT = {
    "UNKNOWN_FACT_INTEGRITY": "BLOCK_DEPENDENT_ACTIONS",
    "UNKNOWN_PERMISSION": "BLOCK_EXECUTION_ONLY",
    # Legacy generic token retained for schema continuity.  In the current
    # public/non-executable model it is an instrument-wide future-execution
    # gate; current research reference-risk is owned separately by the
    # compiler's exact objective-input diagnosis.
    "UNKNOWN_MAX_LOSS": "BLOCK_FUTURE_EXECUTION",
    "UNKNOWN_DIRECTION": "ALLOW_BOUNDED_PROBE",
    "UNKNOWN_CAUSE": "DOES_NOT_BLOCK_BOUNDED_PROBE",
    "UNKNOWN_ACTOR": "BEHAVIOR_HYPOTHESIS_ONLY",
    "UNKNOWN_NARRATIVE_ADOPTION": "REDUCE_NARRATIVE_WEIGHT",
    "UNKNOWN_FUTURE": "NORMAL_MARKET_UNCERTAINTY",
    "UNKNOWN_OUTCOME": "DO_NOT_READ_BEFORE_DUE",
}

HYPOTHESIS_TYPES = (
    "STATE",
    "ATTRIBUTION",
    "FORECAST_PATH",
    "ACTION_THESIS",
)
DIRECTIONS = (
    "LONG",
    "SHORT",
    "RANGE",
    "VOLATILITY",
    "NEUTRAL",
    "OTHER",
    "UNKNOWN",
)
SUBJECTIVE_PLAUSIBILITY_TIERS = (
    "EXTREME_UNCERTAINTY",
    "LOW",
    "HIGH",
)
SUBJECTIVE_TIER_ORDER = {
    tier: index for index, tier in enumerate(SUBJECTIVE_PLAUSIBILITY_TIERS)
}
SUBJECTIVE_TIER_RISK_CAP_UNITS = {
    "EXTREME_UNCERTAINTY": 0,
    "LOW": 50,
    "HIGH": 100,
}
MARKET_REGIME_STATES = (
    "TREND_UP",
    "TREND_DOWN",
    "NEUTRAL",
    "RANGE",
    "CHOPPY",
    "VOLATILITY_WITHOUT_DIRECTION",
    "TRANSITION",
    "OTHER",
    "UNKNOWN",
)
NON_DIRECTIONAL_MARKET_REGIMES = frozenset(
    {
        "NEUTRAL",
        "CHOPPY",
        "VOLATILITY_WITHOUT_DIRECTION",
        "OTHER",
        "UNKNOWN",
    }
)
REGIME_FEATURE_STATES = {
    "DIRECTIONAL_PERSISTENCE": frozenset({"LOW", "HIGH", "UNKNOWN"}),
    "REVERSAL_FREQUENCY": frozenset({"LOW", "HIGH", "UNKNOWN"}),
    "EXECUTION_CHURN_PRESSURE": frozenset({"LOW", "HIGH", "UNKNOWN"}),
    "REALIZED_VOLATILITY": frozenset({"LOW", "HIGH", "UNKNOWN"}),
    "DIRECTIONAL_IMBALANCE": frozenset(
        {"LONG_DOMINANT", "SHORT_DOMINANT", "BALANCED", "UNKNOWN"}
    ),
}
REGIME_FEATURE_REQUIRED_COMBINATIONS = {
    "CHOPPY": {
        "DIRECTIONAL_PERSISTENCE": "LOW",
        "REVERSAL_FREQUENCY": "HIGH",
        "EXECUTION_CHURN_PRESSURE": "HIGH",
    },
    "VOLATILITY_WITHOUT_DIRECTION": {
        "DIRECTIONAL_PERSISTENCE": "LOW",
        "REALIZED_VOLATILITY": "HIGH",
        "DIRECTIONAL_IMBALANCE": "BALANCED",
    },
}
REGIME_FEATURE_REQUIRED_OBSERVABLE_FAMILIES = {
    "DIRECTIONAL_PERSISTENCE": frozenset({"PRICE_ACTION"}),
    "REVERSAL_FREQUENCY": frozenset({"PRICE_ACTION"}),
    "EXECUTION_CHURN_PRESSURE": frozenset(
        {"ORDERBOOK_LIQUIDITY", "TRADE_FLOW"}
    ),
    "REALIZED_VOLATILITY": frozenset({"PRICE_ACTION"}),
    "DIRECTIONAL_IMBALANCE": frozenset(
        {
            "POSITIONING",
            "FUNDING_CROWDING",
            "ORDERBOOK_LIQUIDITY",
            "TRADE_FLOW",
        }
    ),
}
HYPOTHESIS_STATUSES = (
    "ACTIVE",
    "WEAKENED",
    "FALSIFIED",
    "EXPIRED",
    "OTHER",
    "UNKNOWN",
)
ACTIONABLE_HYPOTHESIS_STATUSES = frozenset({"ACTIVE", "WEAKENED", "UNKNOWN"})
ZONE_ROLES = ("SUPPORT", "RESISTANCE", "MAGNET", "BREAKOUT_BOUNDARY")
ZONE_METHODS = (
    "PAST_SWING",
    "RANGE_BOUNDARY",
    "VOLUME_AT_PRICE",
    "ROUND_NUMBER",
    "MULTI_SOURCE_COMPOSITE",
)
ZONE_QUALITIES = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
ZONE_PATH_ROLES = (
    "ZONE_REJECTION",
    "ZONE_ABSORPTION_BREAK",
    "FALSE_BREAK_REVERSION",
    "ZONE_NO_EFFECT_OTHER",
)
FRAME_MODES = ("FULL_CONTEXT", "DELTA_UPDATE")
PATH_MODIFIER_TYPES = (
    "FALSE_BREAK_STOP_RUN",
    "LIQUIDITY_VACUUM",
    "FORCED_LIQUIDATION_CASCADE",
    "CROSS_VENUE_DISLOCATION",
    "VENUE_OR_NETWORK_DISRUPTION",
    "EVENT_SHOCK",
    "ATTENTION_MOMENTUM_FEEDBACK",
    "OTHER",
    "UNKNOWN",
)
PATH_MODIFIER_EFFECTS = (
    "SUPPORTS_PATH",
    "OPPOSES_PATH",
    "MODULATES_PATH",
    "INVALIDATES_PATH",
)
PATH_MODIFIER_STATUSES = ("ACTIVE", "FALSIFIED", "EXPIRED", "UNKNOWN")
MODIFIER_TRIGGER_EFFECTS = (
    "NO_CHANGE",
    "DELAY_TRIGGER",
    "REQUIRE_RECLAIM_CONFIRMATION",
    "CANCEL_TRIGGER",
    "UNKNOWN",
)
MODIFIER_PROTECTION_EFFECTS = (
    "NO_CHANGE",
    "WIDEN_STRESS_BUFFER",
    "REQUIRE_EXIT_REENTRY_SEPARATION",
    "BLOCK_PROTECTION_ASSUMPTION",
    "UNKNOWN",
)
MODIFIER_AFFECTED_ACTION_KINDS = (
    "OPEN_PROBE",
    "ADD",
    "HOLD",
    "REDUCE",
    "CLOSE",
    "REENTER",
    "REVERSE",
    "WAIT",
)
DURABLE_OBJECT_LIMITS = {
    "unknowns": 32,
    "zones": 64,
    "hypotheses": 256,
    "path_modifiers": 128,
    "dependency_clusters": 256,
}

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_UNKNOWN_FIELDS = frozenset(
    {
        "unknown_id",
        "unknown_type",
        "scope",
        "dependency_refs",
        "behavior_effect",
        "explanation",
    }
)
_ZONE_FIELDS = frozenset(
    {
        "zone_id",
        "instrument",
        "role",
        "lower_bound",
        "upper_bound",
        "construction_method",
        "created_at",
        "available_at",
        "expires_at",
        "evidence_refs",
        "dependency_groups",
        "touch_count",
        "touch_refs",
        "reaction_refs",
        "volume_at_price_refs",
        "dwell_time_refs",
        "round_number_refs",
        "orderbook_flow_refs",
        "leverage_refs",
        "options_refs",
        "quality",
        "alternative_zone_ids",
        "path_modifier_ids",
        "path_hypothesis_ids",
        "lineage_id",
        "lineage_revision",
        "predecessor_id",
        "predecessor_fingerprint",
        "semantic_fingerprint",
    }
)
_HYPOTHESIS_FIELDS = frozenset(
    {
        "hypothesis_id",
        "hypothesis_type",
        "direction",
        "scope",
        "regime_scope",
        "mechanism",
        "horizon_seconds",
        "source_refs",
        "dependency_groups",
        "supporting_refs",
        "opposing_refs",
        "opposition_ids",
        "alternative_ids",
        "hard_falsifiers",
        "soft_contradictions",
        "path_modifier_ids",
        "next_observation",
        "expires_at",
        "previous_expires_at",
        "renewal_evidence_refs",
        "parent_revision_digest",
        "status",
        "subjective_plausibility_tier",
        "previous_subjective_plausibility_tier",
        "tier_update_refs",
        "lineage_id",
        "lineage_revision",
        "predecessor_id",
        "predecessor_fingerprint",
        "semantic_fingerprint",
    }
)
_PATH_MODIFIER_FIELDS = frozenset(
    {
        "modifier_id",
        "modifier_type",
        "scope",
        "effect",
        "mechanism",
        "source_refs",
        "dependency_groups",
        "affected_hypothesis_ids",
        "affected_zone_ids",
        "affected_action_kinds",
        "conditions",
        "trigger_effect",
        "protection_effect",
        "invalidators",
        "created_at",
        "available_at",
        "expires_at",
        "status",
        "lineage_id",
        "lineage_revision",
        "predecessor_id",
        "predecessor_fingerprint",
        "semantic_fingerprint",
    }
)
_CLUSTER_FIELDS = frozenset(
    {
        "cluster_id",
        "member_hypothesis_ids",
        "direction",
        "shared_dependency_groups",
        "aggregate_tier",
        "aggregation_method",
    }
)
_MARKET_REGIME_FIELDS = frozenset(
    {
        "regime",
        "evidence_refs",
        "counter_evidence_refs",
        "regime_feature_assessments",
        "expires_at",
        "previous_regime",
        "transition_evidence_refs",
    }
)
_REGIME_FEATURE_ASSESSMENT_FIELDS = frozenset(
    {"feature_type", "feature_state", "evidence_refs"}
)
_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "as_of",
        "frame_mode",
        "previous_state_digest",
        "market_regime_state",
        "unknowns",
        "zones",
        "hypotheses",
        "path_modifiers",
        "dependency_clusters",
        "required_hypothesis_types",
        "opposing_direction_policy",
        "residual_policy",
        "subjective_tier_policy",
        "expiry_policy",
        "modifier_policy",
        "resource_limits",
        "resource_policy",
        "probability_claim",
        "brier_ece_allowed",
        "expected_value_allowed",
        "source_scope",
        "external_execution_authority",
        "executable",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32DynamicResearchError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DynamicResearchError(code) from exc
    if parsed.tzinfo is None:
        raise V32DynamicResearchError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32DynamicResearchError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(UTC)


def _optional_time(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _time(value, code)


def _digest(value: Any, code: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32DynamicResearchError(code)
    return value


def _strings(values: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise V32DynamicResearchError(code)
    result = [_text(item, code) for item in values]
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise V32DynamicResearchError(code)
    return sorted(result)


def _optional_text(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _text(value, code)


def _lineage_metadata(
    row: Mapping[str, Any],
    *,
    object_id: str,
    expected_fingerprint: str,
    code: str,
) -> dict[str, Any]:
    lineage_id = _text(row["lineage_id"], code)
    revision = row["lineage_revision"]
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or not 1 <= revision <= 1_000_000
    ):
        raise V32DynamicResearchError(code)
    predecessor_id = _optional_text(row["predecessor_id"], code)
    predecessor_fingerprint = _digest(
        row["predecessor_fingerprint"], code, nullable=True
    )
    if (predecessor_id is None) != (predecessor_fingerprint is None):
        raise V32DynamicResearchError(code)
    if revision == 1:
        if predecessor_id is not None or lineage_id != object_id:
            raise V32DynamicResearchError("V32_LINEAGE_GENESIS_INVALID")
    elif predecessor_id is None:
        raise V32DynamicResearchError("V32_LINEAGE_PREDECESSOR_REQUIRED")
    supplied_fingerprint = row["semantic_fingerprint"]
    if supplied_fingerprint is not None and _digest(
        supplied_fingerprint, code
    ) != expected_fingerprint:
        raise V32DynamicResearchError("V32_SEMANTIC_FINGERPRINT_MISMATCH")
    return {
        "lineage_id": lineage_id,
        "lineage_revision": revision,
        "predecessor_id": predecessor_id,
        "predecessor_fingerprint": predecessor_fingerprint,
        "semantic_fingerprint": expected_fingerprint,
    }


def _hypothesis_fingerprint(row: Mapping[str, Any]) -> str:
    # Free-form mechanism prose is deliberately excluded.  Otherwise an Agent
    # could append punctuation to an expired thesis and evade renewal lineage.
    return canonical_digest(
        {
            "fingerprint_schema": "V32_HYPOTHESIS_SEMANTIC_FINGERPRINT_V1",
            "hypothesis_type": row["hypothesis_type"],
            "direction": row["direction"],
            "scope": row["scope"],
            "regime_scope": row["regime_scope"],
            "horizon_seconds": row["horizon_seconds"],
            "dependency_groups": row["dependency_groups"],
            "hard_falsifiers": row["hard_falsifiers"],
            "next_observation": row["next_observation"],
        }
    )


def _zone_fingerprint(row: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "fingerprint_schema": "V32_ZONE_SEMANTIC_FINGERPRINT_V1",
            "instrument": row["instrument"],
            "role": row["role"],
            "lower_bound": row["lower_bound"],
            "upper_bound": row["upper_bound"],
            "construction_method": row["construction_method"],
            "dependency_groups": row["dependency_groups"],
        }
    )


def _modifier_fingerprint(row: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "fingerprint_schema": "V32_PATH_MODIFIER_SEMANTIC_FINGERPRINT_V1",
            "modifier_type": row["modifier_type"],
            "scope": row["scope"],
            "effect": row["effect"],
            "dependency_groups": row["dependency_groups"],
            "affected_action_kinds": row["affected_action_kinds"],
            "conditions": row["conditions"],
            "trigger_effect": row["trigger_effect"],
            "protection_effect": row["protection_effect"],
            "invalidators": row["invalidators"],
        }
    )


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, (float, bool)):
        raise V32DynamicResearchError(code)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V32DynamicResearchError(code) from exc
    if not parsed.is_finite():
        raise V32DynamicResearchError(code)
    return parsed


def _unknown(row: Any) -> dict[str, Any]:
    code = "V32_UNKNOWN_ROW_INVALID"
    if not isinstance(row, Mapping) or set(row) != _UNKNOWN_FIELDS:
        raise V32DynamicResearchError(code)
    unknown_type = _text(row["unknown_type"], code)
    if unknown_type not in UNKNOWN_TYPES:
        raise V32DynamicResearchError(code)
    result = {
        "unknown_id": _text(row["unknown_id"], code),
        "unknown_type": unknown_type,
        "scope": _text(row["scope"], code),
        "dependency_refs": _strings(row["dependency_refs"], code),
        "behavior_effect": _text(row["behavior_effect"], code),
        "explanation": _text(row["explanation"], code),
    }
    if result["behavior_effect"] != UNKNOWN_BEHAVIOR_EFFECT[unknown_type]:
        raise V32DynamicResearchError("V32_UNKNOWN_BEHAVIOR_EFFECT_INVALID")
    return result


def _zone(row: Any, *, as_of: datetime) -> dict[str, Any]:
    code = "V32_ZONE_ROW_INVALID"
    if not isinstance(row, Mapping) or set(row) != _ZONE_FIELDS:
        raise V32DynamicResearchError(code)
    role = _text(row["role"], code)
    method = _text(row["construction_method"], code)
    quality = _text(row["quality"], code)
    if (
        role not in ZONE_ROLES
        or method not in ZONE_METHODS
        or quality not in ZONE_QUALITIES
    ):
        raise V32DynamicResearchError(code)
    lower = _decimal(row["lower_bound"], code)
    upper = _decimal(row["upper_bound"], code)
    if lower <= 0 or upper <= lower:
        raise V32DynamicResearchError("V32_ZONE_BOUNDS_INVALID")
    created = _moment(row["created_at"], code)
    available = _moment(row["available_at"], code)
    expires = _moment(row["expires_at"], code)
    # Expired zones remain admissible as immutable audit tombstones.  Cross-
    # cycle continuity owns their retirement and prevents an old identity from
    # being extended or revived.  A zone can never expire before it became
    # available, and only non-expired zones may support a current action plan.
    if created > available or available > as_of or expires <= available:
        raise V32DynamicResearchError("V32_ZONE_TIME_INVALID")
    touch_count = row["touch_count"]
    if (
        isinstance(touch_count, bool)
        or not isinstance(touch_count, int)
        or touch_count < 0
    ):
        raise V32DynamicResearchError(code)
    touch_refs = _strings(row["touch_refs"], code, allow_empty=True)
    if len(touch_refs) != touch_count:
        raise V32DynamicResearchError("V32_ZONE_TOUCH_LEDGER_INVALID")
    paths = row["path_hypothesis_ids"]
    if not isinstance(paths, Mapping) or set(paths) != set(ZONE_PATH_ROLES):
        raise V32DynamicResearchError("V32_ZONE_PATH_SET_INVALID")
    path_ids = [paths[name] for name in ZONE_PATH_ROLES]
    if len(path_ids) != len(set(path_ids)):
        raise V32DynamicResearchError("V32_ZONE_PATH_SET_INVALID")
    zone_id = _text(row["zone_id"], code)
    result = {
        "zone_id": zone_id,
        "instrument": _text(row["instrument"], code),
        "role": role,
        "lower_bound": canonical_decimal(lower),
        "upper_bound": canonical_decimal(upper),
        "construction_method": method,
        "created_at": _time(row["created_at"], code),
        "available_at": _time(row["available_at"], code),
        "expires_at": _time(row["expires_at"], code),
        "evidence_refs": _strings(row["evidence_refs"], code),
        "dependency_groups": _strings(row["dependency_groups"], code),
        "touch_count": touch_count,
        "touch_refs": touch_refs,
        "reaction_refs": _strings(row["reaction_refs"], code, allow_empty=True),
        "volume_at_price_refs": _strings(
            row["volume_at_price_refs"], code, allow_empty=True
        ),
        "dwell_time_refs": _strings(row["dwell_time_refs"], code, allow_empty=True),
        "round_number_refs": _strings(
            row["round_number_refs"], code, allow_empty=True
        ),
        "orderbook_flow_refs": _strings(
            row["orderbook_flow_refs"], code, allow_empty=True
        ),
        "leverage_refs": _strings(row["leverage_refs"], code, allow_empty=True),
        "options_refs": _strings(row["options_refs"], code, allow_empty=True),
        "quality": quality,
        "alternative_zone_ids": _strings(
            row["alternative_zone_ids"], code, allow_empty=True
        ),
        "path_modifier_ids": _strings(
            row["path_modifier_ids"], code, allow_empty=True
        ),
        "path_hypothesis_ids": {
            name: _text(paths[name], "V32_ZONE_PATH_SET_INVALID")
            for name in ZONE_PATH_ROLES
        },
    }
    result.update(
        _lineage_metadata(
            row,
            object_id=zone_id,
            expected_fingerprint=_zone_fingerprint(result),
            code="V32_ZONE_LINEAGE_INVALID",
        )
    )
    return result


def _hypothesis(row: Any, *, as_of: datetime) -> dict[str, Any]:
    code = "V32_HYPOTHESIS_ROW_INVALID"
    if not isinstance(row, Mapping) or set(row) != _HYPOTHESIS_FIELDS:
        raise V32DynamicResearchError(code)
    hypothesis_type = _text(row["hypothesis_type"], code)
    direction = _text(row["direction"], code)
    status = _text(row["status"], code)
    if (
        hypothesis_type not in HYPOTHESIS_TYPES
        or direction not in DIRECTIONS
        or status not in HYPOTHESIS_STATUSES
    ):
        raise V32DynamicResearchError(code)
    horizon = row["horizon_seconds"]
    if (
        isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or not 60 <= horizon <= 604800
    ):
        raise V32DynamicResearchError("V32_HYPOTHESIS_HORIZON_INVALID")
    expires = _moment(row["expires_at"], code)
    if status == "EXPIRED" and expires > as_of:
        raise V32DynamicResearchError("V32_HYPOTHESIS_EXPIRY_INVALID")
    if status not in {"FALSIFIED", "EXPIRED"} and expires <= as_of:
        raise V32DynamicResearchError("V32_HYPOTHESIS_EXPIRY_INVALID")
    tier = _text(row["subjective_plausibility_tier"], code)
    previous_tier = _optional_text(
        row["previous_subjective_plausibility_tier"], code
    )
    if tier not in SUBJECTIVE_PLAUSIBILITY_TIERS:
        raise V32DynamicResearchError("V32_HYPOTHESIS_TIER_INVALID")
    if (
        previous_tier is not None
        and previous_tier not in SUBJECTIVE_PLAUSIBILITY_TIERS
    ):
        raise V32DynamicResearchError("V32_HYPOTHESIS_PREVIOUS_TIER_INVALID")
    update_refs = _strings(row["tier_update_refs"], code, allow_empty=True)
    if status in {"FALSIFIED", "EXPIRED"} and tier != "EXTREME_UNCERTAINTY":
        raise V32DynamicResearchError("V32_TERMINAL_HYPOTHESIS_TIER_MUST_BE_ZERO_RISK")
    opposition_ids = _strings(row["opposition_ids"], code, allow_empty=True)
    if direction in {"LONG", "SHORT"} and not opposition_ids:
        raise V32DynamicResearchError("V32_DIRECTIONAL_OPPOSITION_REQUIRED")
    if direction not in {"LONG", "SHORT"} and opposition_ids:
        raise V32DynamicResearchError("V32_NONDIRECTIONAL_OPPOSITION_FORBIDDEN")
    parent = _digest(row["parent_revision_digest"], code, nullable=True)
    previous_expires_at = _optional_time(
        row["previous_expires_at"], "V32_HYPOTHESIS_PREVIOUS_EXPIRY_INVALID"
    )
    hypothesis_id = _text(row["hypothesis_id"], code)
    result = {
        "hypothesis_id": hypothesis_id,
        "hypothesis_type": hypothesis_type,
        "direction": direction,
        "scope": _text(row["scope"], code),
        "regime_scope": _strings(row["regime_scope"], code),
        "mechanism": _text(row["mechanism"], code),
        "horizon_seconds": horizon,
        "source_refs": _strings(row["source_refs"], code),
        "dependency_groups": _strings(row["dependency_groups"], code),
        "supporting_refs": _strings(row["supporting_refs"], code, allow_empty=True),
        "opposing_refs": _strings(row["opposing_refs"], code, allow_empty=True),
        "opposition_ids": opposition_ids,
        "alternative_ids": _strings(row["alternative_ids"], code, allow_empty=True),
        "hard_falsifiers": _strings(row["hard_falsifiers"], code),
        "soft_contradictions": _strings(
            row["soft_contradictions"], code, allow_empty=True
        ),
        "path_modifier_ids": _strings(
            row["path_modifier_ids"], code, allow_empty=True
        ),
        "next_observation": _text(row["next_observation"], code),
        "expires_at": _time(row["expires_at"], code),
        "previous_expires_at": previous_expires_at,
        "renewal_evidence_refs": _strings(
            row["renewal_evidence_refs"], code, allow_empty=True
        ),
        "parent_revision_digest": parent,
        "status": status,
        "subjective_plausibility_tier": tier,
        "previous_subjective_plausibility_tier": previous_tier,
        "tier_update_refs": update_refs,
    }
    result.update(
        _lineage_metadata(
            row,
            object_id=hypothesis_id,
            expected_fingerprint=_hypothesis_fingerprint(result),
            code="V32_HYPOTHESIS_LINEAGE_INVALID",
        )
    )
    return result


def _path_modifier(row: Any, *, as_of: datetime) -> dict[str, Any]:
    code = "V32_PATH_MODIFIER_ROW_INVALID"
    if not isinstance(row, Mapping) or set(row) != _PATH_MODIFIER_FIELDS:
        raise V32DynamicResearchError(code)
    modifier_type = _text(row["modifier_type"], code)
    effect = _text(row["effect"], code)
    status = _text(row["status"], code)
    if (
        modifier_type not in PATH_MODIFIER_TYPES
        or effect not in PATH_MODIFIER_EFFECTS
        or status not in PATH_MODIFIER_STATUSES
    ):
        raise V32DynamicResearchError(code)
    created = _moment(row["created_at"], code)
    available = _moment(row["available_at"], code)
    expires = _moment(row["expires_at"], code)
    if created > available or available > as_of:
        raise V32DynamicResearchError("V32_PATH_MODIFIER_TIME_INVALID")
    if status == "EXPIRED" and expires > as_of:
        raise V32DynamicResearchError("V32_PATH_MODIFIER_TIME_INVALID")
    if status not in {"FALSIFIED", "EXPIRED"} and expires <= as_of:
        raise V32DynamicResearchError("V32_PATH_MODIFIER_TIME_INVALID")
    trigger_effect = _text(row["trigger_effect"], code)
    protection_effect = _text(row["protection_effect"], code)
    affected_actions = _strings(row["affected_action_kinds"], code)
    if (
        trigger_effect not in MODIFIER_TRIGGER_EFFECTS
        or protection_effect not in MODIFIER_PROTECTION_EFFECTS
        or any(item not in MODIFIER_AFFECTED_ACTION_KINDS for item in affected_actions)
    ):
        raise V32DynamicResearchError("V32_PATH_MODIFIER_TYPED_EFFECT_INVALID")
    modifier_id = _text(row["modifier_id"], code)
    result = {
        "modifier_id": modifier_id,
        "modifier_type": modifier_type,
        "scope": _text(row["scope"], code),
        "effect": effect,
        "mechanism": _text(row["mechanism"], code),
        "source_refs": _strings(row["source_refs"], code),
        "dependency_groups": _strings(row["dependency_groups"], code),
        "affected_hypothesis_ids": _strings(
            row["affected_hypothesis_ids"], code
        ),
        "affected_zone_ids": _strings(
            row["affected_zone_ids"], code, allow_empty=True
        ),
        "affected_action_kinds": affected_actions,
        "conditions": _strings(row["conditions"], code),
        "trigger_effect": trigger_effect,
        "protection_effect": protection_effect,
        "invalidators": _strings(row["invalidators"], code),
        "created_at": _time(row["created_at"], code),
        "available_at": _time(row["available_at"], code),
        "expires_at": _time(row["expires_at"], code),
        "status": status,
    }
    result.update(
        _lineage_metadata(
            row,
            object_id=modifier_id,
            expected_fingerprint=_modifier_fingerprint(result),
            code="V32_PATH_MODIFIER_LINEAGE_INVALID",
        )
    )
    return result


def _cluster(row: Any, *, hypotheses: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    code = "V32_CLUSTER_ROW_INVALID"
    if not isinstance(row, Mapping) or set(row) != _CLUSTER_FIELDS:
        raise V32DynamicResearchError(code)
    members = _strings(row["member_hypothesis_ids"], code)
    if any(member not in hypotheses for member in members):
        raise V32DynamicResearchError("V32_CLUSTER_MEMBER_INVALID")
    direction = _text(row["direction"], code)
    if direction not in DIRECTIONS or direction in {"OTHER", "UNKNOWN"}:
        raise V32DynamicResearchError(code)
    if any(hypotheses[member]["direction"] != direction for member in members):
        raise V32DynamicResearchError("V32_CLUSTER_DIRECTION_INVALID")
    shared_groups = _strings(row["shared_dependency_groups"], code)
    member_groups = [set(hypotheses[member]["dependency_groups"]) for member in members]
    intersection = set.intersection(*member_groups)
    if not set(shared_groups).issubset(intersection):
        raise V32DynamicResearchError("V32_CLUSTER_DEPENDENCY_INVALID")
    aggregate = _text(row["aggregate_tier"], code)
    expected = max(
        (
            hypotheses[member]["subjective_plausibility_tier"]
            for member in members
            if hypotheses[member]["status"] in ACTIONABLE_HYPOTHESIS_STATUSES
        ),
        key=lambda tier: SUBJECTIVE_TIER_ORDER[tier],
        default="EXTREME_UNCERTAINTY",
    )
    if (
        aggregate not in SUBJECTIVE_PLAUSIBILITY_TIERS
        or aggregate != expected
        or row["aggregation_method"]
        != "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM"
    ):
        raise V32DynamicResearchError("V32_CLUSTER_AGGREGATION_INVALID")
    return {
        "cluster_id": _text(row["cluster_id"], code),
        "member_hypothesis_ids": members,
        "direction": direction,
        "shared_dependency_groups": shared_groups,
        "aggregate_tier": expected,
        "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
    }


def _market_regime_state(
    row: Any,
    *,
    as_of: datetime,
    cycle_index: int,
) -> dict[str, Any]:
    code = "V32_MARKET_REGIME_STATE_INVALID"
    if not isinstance(row, Mapping) or set(row) != _MARKET_REGIME_FIELDS:
        raise V32DynamicResearchError(code)
    regime = _text(row["regime"], code)
    previous_regime = _optional_text(row["previous_regime"], code)
    if regime not in MARKET_REGIME_STATES or (
        previous_regime is not None and previous_regime not in MARKET_REGIME_STATES
    ):
        raise V32DynamicResearchError(code)
    evidence_refs = _strings(row["evidence_refs"], code)
    counter_evidence_refs = _strings(row["counter_evidence_refs"], code)
    feature_rows = row["regime_feature_assessments"]
    if isinstance(feature_rows, (str, bytes)) or not isinstance(
        feature_rows, Sequence
    ):
        raise V32DynamicResearchError(code)
    feature_assessments: list[dict[str, Any]] = []
    for feature_row in feature_rows:
        feature_code = "V32_MARKET_REGIME_FEATURE_ASSESSMENT_INVALID"
        if (
            not isinstance(feature_row, Mapping)
            or set(feature_row) != _REGIME_FEATURE_ASSESSMENT_FIELDS
        ):
            raise V32DynamicResearchError(feature_code)
        feature_type = _text(feature_row["feature_type"], feature_code)
        feature_state = _text(feature_row["feature_state"], feature_code)
        if (
            feature_type not in REGIME_FEATURE_STATES
            or feature_state not in REGIME_FEATURE_STATES[feature_type]
        ):
            raise V32DynamicResearchError(feature_code)
        feature_assessments.append(
            {
                "feature_type": feature_type,
                "feature_state": feature_state,
                "evidence_refs": _strings(
                    feature_row["evidence_refs"], feature_code
                ),
            }
        )
    feature_types = [row["feature_type"] for row in feature_assessments]
    if len(feature_types) != len(set(feature_types)):
        raise V32DynamicResearchError(
            "V32_MARKET_REGIME_FEATURE_ASSESSMENT_DUPLICATE"
        )
    feature_assessments.sort(key=lambda item: item["feature_type"])
    feature_by_type = {
        item["feature_type"]: item for item in feature_assessments
    }
    required_combination = REGIME_FEATURE_REQUIRED_COMBINATIONS.get(regime, {})
    if any(
        feature_type not in feature_by_type
        or feature_by_type[feature_type]["feature_state"] != required_state
        for feature_type, required_state in required_combination.items()
    ):
        raise V32DynamicResearchError(
            "V32_MARKET_REGIME_FEATURE_COMBINATION_INVALID"
        )
    feature_evidence_refs = {
        evidence_ref
        for assessment in feature_assessments
        for evidence_ref in assessment["evidence_refs"]
    }
    if (
        not feature_evidence_refs.issubset(evidence_refs)
        or (required_combination and len(feature_evidence_refs) < 2)
    ):
        raise V32DynamicResearchError(
            "V32_MARKET_REGIME_FEATURE_EVIDENCE_INVALID"
        )
    transition_refs = _strings(
        row["transition_evidence_refs"], code, allow_empty=True
    )
    if set(evidence_refs).intersection(counter_evidence_refs):
        raise V32DynamicResearchError("V32_MARKET_REGIME_EVIDENCE_OVERLAP")
    expires_at = _time(row["expires_at"], code)
    if _moment(expires_at, code) <= as_of:
        raise V32DynamicResearchError("V32_MARKET_REGIME_EXPIRED")
    if cycle_index == 1:
        if previous_regime is not None or transition_refs:
            raise V32DynamicResearchError("V32_INITIAL_MARKET_REGIME_BINDING_INVALID")
    elif previous_regime is None:
        raise V32DynamicResearchError("V32_MARKET_REGIME_PREDECESSOR_REQUIRED")
    elif regime == previous_regime:
        if transition_refs:
            raise V32DynamicResearchError("V32_MARKET_REGIME_FALSE_TRANSITION")
    elif not transition_refs:
        raise V32DynamicResearchError("V32_MARKET_REGIME_TRANSITION_EVIDENCE_REQUIRED")
    elif required_combination and not feature_evidence_refs.issubset(
        transition_refs
    ):
        raise V32DynamicResearchError(
            "V32_MARKET_REGIME_FEATURE_TRANSITION_BINDING_INVALID"
        )
    return {
        "regime": regime,
        "evidence_refs": evidence_refs,
        "counter_evidence_refs": counter_evidence_refs,
        "regime_feature_assessments": feature_assessments,
        "expires_at": expires_at,
        "previous_regime": previous_regime,
        "transition_evidence_refs": transition_refs,
    }


def _validate_lineage_graph(
    rows: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    active: Any,
) -> None:
    by_id = {str(row[id_field]): row for row in rows}
    lineage_revisions = [
        (str(row["lineage_id"]), int(row["lineage_revision"])) for row in rows
    ]
    predecessor_ids = [
        str(row["predecessor_id"])
        for row in rows
        if row["predecessor_id"] is not None
    ]
    if (
        len(lineage_revisions) != len(set(lineage_revisions))
        or len(predecessor_ids) != len(set(predecessor_ids))
    ):
        raise V32DynamicResearchError("V32_LINEAGE_GRAPH_INVALID")
    for row in rows:
        if row["lineage_revision"] == 1:
            continue
        predecessor = by_id.get(str(row["predecessor_id"]))
        if (
            predecessor is None
            or predecessor["lineage_id"] != row["lineage_id"]
            or predecessor["lineage_revision"] + 1 != row["lineage_revision"]
            or predecessor["semantic_fingerprint"]
            != row["predecessor_fingerprint"]
            or predecessor["semantic_fingerprint"] != row["semantic_fingerprint"]
        ):
            raise V32DynamicResearchError("V32_LINEAGE_GRAPH_INVALID")
    active_lineages = [
        str(row["lineage_id"]) for row in rows if active(row)
    ]
    if len(active_lineages) != len(set(active_lineages)):
        raise V32DynamicResearchError("V32_LINEAGE_MULTIPLE_ACTIVE_REVISIONS")


def build_v32_dynamic_research_state_v1(
    *,
    run_id: str,
    cycle_index: int,
    as_of: str,
    frame_mode: str,
    previous_state_digest: str | None,
    market_regime_state: Mapping[str, Any],
    unknowns: Sequence[Mapping[str, Any]],
    zones: Sequence[Mapping[str, Any]],
    hypotheses: Sequence[Mapping[str, Any]],
    path_modifiers: Sequence[Mapping[str, Any]],
    dependency_clusters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one complete state with typed regimes and ordinal Agent tiers."""

    for name, values in (
        ("unknowns", unknowns),
        ("zones", zones),
        ("hypotheses", hypotheses),
        ("path_modifiers", path_modifiers),
        ("dependency_clusters", dependency_clusters),
    ):
        if (
            isinstance(values, (str, bytes))
            or not isinstance(values, Sequence)
            or len(values) > DURABLE_OBJECT_LIMITS[name]
        ):
            raise V32DynamicResearchError("V32_STATE_DURABLE_OBJECT_LIMIT_EXCEEDED")

    run = _text(run_id, "V32_STATE_RUN_ID_INVALID")
    if (
        isinstance(cycle_index, bool)
        or not isinstance(cycle_index, int)
        or not 1 <= cycle_index <= 1000000
    ):
        raise V32DynamicResearchError("V32_STATE_CYCLE_INVALID")
    if frame_mode not in FRAME_MODES:
        raise V32DynamicResearchError("V32_STATE_FRAME_MODE_INVALID")
    previous = _digest(
        previous_state_digest, "V32_STATE_PREVIOUS_DIGEST_INVALID", nullable=True
    )
    if (cycle_index == 1 and (frame_mode != "FULL_CONTEXT" or previous is not None)) or (
        cycle_index > 1 and previous is None
    ):
        raise V32DynamicResearchError("V32_STATE_PREVIOUS_BINDING_INVALID")
    as_of_text = _time(as_of, "V32_STATE_AS_OF_INVALID")
    as_of_moment = _moment(as_of_text, "V32_STATE_AS_OF_INVALID")
    normalized_regime = _market_regime_state(
        market_regime_state,
        as_of=as_of_moment,
        cycle_index=cycle_index,
    )

    normalized_unknowns = [_unknown(row) for row in unknowns]
    normalized_zones = [_zone(row, as_of=as_of_moment) for row in zones]
    normalized_hypotheses = [
        _hypothesis(row, as_of=as_of_moment) for row in hypotheses
    ]
    normalized_modifiers = [
        _path_modifier(row, as_of=as_of_moment) for row in path_modifiers
    ]
    for rows, key, code in (
        (normalized_unknowns, "unknown_id", "V32_UNKNOWN_ID_DUPLICATE"),
        (normalized_zones, "zone_id", "V32_ZONE_ID_DUPLICATE"),
        (normalized_hypotheses, "hypothesis_id", "V32_HYPOTHESIS_ID_DUPLICATE"),
    ):
        values = [row[key] for row in rows]
        if len(values) != len(set(values)):
            raise V32DynamicResearchError(code)
    hypothesis_map = {
        row["hypothesis_id"]: row for row in normalized_hypotheses
    }
    zone_map = {row["zone_id"]: row for row in normalized_zones}
    modifier_ids = [row["modifier_id"] for row in normalized_modifiers]
    if len(modifier_ids) != len(set(modifier_ids)):
        raise V32DynamicResearchError("V32_PATH_MODIFIER_ID_DUPLICATE")
    modifier_map = {row["modifier_id"]: row for row in normalized_modifiers}
    _validate_lineage_graph(
        normalized_hypotheses,
        id_field="hypothesis_id",
        active=lambda row: row["status"] not in {"FALSIFIED", "EXPIRED"},
    )
    _validate_lineage_graph(
        normalized_zones,
        id_field="zone_id",
        active=lambda row: _moment(row["expires_at"], "V32_ZONE_TIME_INVALID")
        > as_of_moment,
    )
    _validate_lineage_graph(
        normalized_modifiers,
        id_field="modifier_id",
        active=lambda row: row["status"] in {"ACTIVE", "UNKNOWN"},
    )
    if set(row["hypothesis_type"] for row in normalized_hypotheses) != set(
        HYPOTHESIS_TYPES
    ):
        raise V32DynamicResearchError("V32_HYPOTHESIS_TYPE_SET_INCOMPLETE")
    residual_directions = [
        row["direction"]
        for row in normalized_hypotheses
        if row["direction"] in {"OTHER", "UNKNOWN"}
    ]
    if (
        residual_directions.count("OTHER") != 1
        or residual_directions.count("UNKNOWN") != 1
    ):
        raise V32DynamicResearchError("V32_HYPOTHESIS_RESIDUAL_SET_INVALID")

    for hypothesis in normalized_hypotheses:
        hypothesis_id = hypothesis["hypothesis_id"]
        parent = hypothesis["parent_revision_digest"]
        tier = hypothesis["subjective_plausibility_tier"]
        prior_tier = hypothesis["previous_subjective_plausibility_tier"]
        update_refs = hypothesis["tier_update_refs"]
        previous_expiry = hypothesis["previous_expires_at"]
        renewal_refs = hypothesis["renewal_evidence_refs"]
        if cycle_index == 1:
            if (
                parent is not None
                or prior_tier is not None
                or previous_expiry is not None
                or update_refs
                or renewal_refs
            ):
                raise V32DynamicResearchError("V32_INITIAL_TIER_BINDING_INVALID")
        elif parent is None:
            if (
                prior_tier is not None
                or previous_expiry is not None
                or update_refs
                or renewal_refs
            ):
                raise V32DynamicResearchError(
                    "V32_NEW_HYPOTHESIS_TIER_BINDING_INVALID"
                )
        elif (
            parent != previous
            or prior_tier is None
            or previous_expiry is None
        ):
            raise V32DynamicResearchError("V32_REVISED_HYPOTHESIS_TIER_BINDING_INVALID")
        elif abs(
            SUBJECTIVE_TIER_ORDER[tier] - SUBJECTIVE_TIER_ORDER[prior_tier]
        ) > 1:
            raise V32DynamicResearchError("V32_HYPOTHESIS_TIER_JUMP_FORBIDDEN")
        elif tier != prior_tier and not update_refs:
            raise V32DynamicResearchError("V32_HYPOTHESIS_TIER_UPDATE_EVIDENCE_REQUIRED")
        elif tier == prior_tier and update_refs:
            raise V32DynamicResearchError("V32_HYPOTHESIS_FALSE_TIER_UPDATE_INVALID")

        # HIGH is an operational support tier, not free-form rhetoric.  The
        # domain can prove the required evidence cardinality, explicit counter
        # evidence, and declared dependency diversity.  Cross-cycle freshness
        # and actual non-overlap of graph dependency closures are verified by
        # the continuity composition against sealed registries.
        initial_high = tier == "HIGH" and parent is None
        low_to_high = tier == "HIGH" and prior_tier == "LOW"
        if initial_high:
            high_refs = set(hypothesis["source_refs"]) | set(
                hypothesis["supporting_refs"]
            )
            if (
                len(high_refs) < 2
                or len(hypothesis["dependency_groups"]) < 2
                or not hypothesis["opposing_refs"]
            ):
                raise V32DynamicResearchError(
                    "V32_HIGH_TIER_DUAL_EVIDENCE_AND_COUNTER_REQUIRED"
                )
        if low_to_high:
            if (
                len(update_refs) < 2
                or not set(update_refs).issubset(
                    set(hypothesis["source_refs"])
                    | set(hypothesis["supporting_refs"])
                )
                or len(hypothesis["dependency_groups"]) < 2
                or not hypothesis["opposing_refs"]
            ):
                raise V32DynamicResearchError(
                    "V32_LOW_TO_HIGH_DUAL_EVIDENCE_AND_COUNTER_REQUIRED"
                )
        if parent is not None and _moment(hypothesis["expires_at"], "V32_HYPOTHESIS_EXPIRY_INVALID") > _moment(
            previous_expiry, "V32_HYPOTHESIS_PREVIOUS_EXPIRY_INVALID"
        ):
            if not renewal_refs or not set(renewal_refs).issubset(
                hypothesis["supporting_refs"]
            ):
                raise V32DynamicResearchError(
                    "V32_HYPOTHESIS_RENEWAL_EVIDENCE_REQUIRED"
                )
        elif renewal_refs:
            raise V32DynamicResearchError("V32_HYPOTHESIS_FALSE_RENEWAL_INVALID")

        alternatives = hypothesis["alternative_ids"]
        if hypothesis_id in alternatives or any(
            alternative_id not in hypothesis_map for alternative_id in alternatives
        ):
            raise V32DynamicResearchError("V32_HYPOTHESIS_ALTERNATIVE_INVALID")
        if not set(hypothesis["opposition_ids"]).issubset(alternatives):
            raise V32DynamicResearchError("V32_HYPOTHESIS_ALTERNATIVE_INVALID")
        for opposition_id in hypothesis["opposition_ids"]:
            opposition = hypothesis_map.get(opposition_id)
            if (
                opposition is None
                or hypothesis_id not in opposition["opposition_ids"]
                or hypothesis["direction"] == opposition["direction"]
                or {
                    hypothesis["direction"],
                    opposition["direction"],
                }
                != {"LONG", "SHORT"}
                or hypothesis["hypothesis_type"] != opposition["hypothesis_type"]
                or hypothesis["scope"] != opposition["scope"]
                or hypothesis["horizon_seconds"] != opposition["horizon_seconds"]
                or hypothesis["regime_scope"] != opposition["regime_scope"]
            ):
                raise V32DynamicResearchError("V32_HYPOTHESIS_OPPOSITION_INVALID")

    non_residual_ids = {
        row["hypothesis_id"]
        for row in normalized_hypotheses
        if row["direction"] not in {"OTHER", "UNKNOWN"}
    }
    for modifier in normalized_modifiers:
        modifier_id = modifier["modifier_id"]
        affected_ids = set(modifier["affected_hypothesis_ids"])
        affected_zone_ids = set(modifier["affected_zone_ids"])
        if (
            not affected_ids.issubset(non_residual_ids)
            or affected_ids == non_residual_ids
            or not affected_zone_ids.issubset(zone_map)
        ):
            raise V32DynamicResearchError(
                "V32_PATH_MODIFIER_AFFECTED_SET_INVALID"
            )
        modifier_dependencies = set(modifier["dependency_groups"])
        for hypothesis_id in affected_ids:
            hypothesis = hypothesis_map[hypothesis_id]
            if (
                modifier_id not in hypothesis["path_modifier_ids"]
                or not modifier_dependencies.intersection(
                    hypothesis["dependency_groups"]
                )
            ):
                raise V32DynamicResearchError(
                    "V32_PATH_MODIFIER_DEPENDENCY_BINDING_INVALID"
                )
        for zone_id in affected_zone_ids:
            zone = zone_map[zone_id]
            zone_path_ids = set(zone["path_hypothesis_ids"].values())
            if (
                modifier_id not in zone["path_modifier_ids"]
                or not modifier_dependencies.intersection(
                    zone["dependency_groups"]
                )
                or not affected_ids.intersection(zone_path_ids)
            ):
                raise V32DynamicResearchError(
                    "V32_PATH_MODIFIER_ZONE_BINDING_INVALID"
                )
    for hypothesis in normalized_hypotheses:
        for modifier_id in hypothesis["path_modifier_ids"]:
            modifier = modifier_map.get(modifier_id)
            if (
                modifier is None
                or hypothesis["hypothesis_id"]
                not in modifier["affected_hypothesis_ids"]
            ):
                raise V32DynamicResearchError(
                    "V32_HYPOTHESIS_PATH_MODIFIER_BINDING_INVALID"
                )

    for zone in normalized_zones:
        zone_id = zone["zone_id"]
        if zone_id in zone["alternative_zone_ids"] or any(
            alternative_id not in zone_map
            for alternative_id in zone["alternative_zone_ids"]
        ):
            raise V32DynamicResearchError("V32_ZONE_ALTERNATIVE_INVALID")
        paths = {
            path_role: hypothesis_map.get(hypothesis_id)
            for path_role, hypothesis_id in zone["path_hypothesis_ids"].items()
        }
        if any(path is None for path in paths.values()):
            raise V32DynamicResearchError("V32_ZONE_PATH_HYPOTHESIS_INVALID")
        if any(
            path["hypothesis_type"] != "FORECAST_PATH"
            for path in paths.values()
            if path is not None
        ):
            raise V32DynamicResearchError("V32_ZONE_PATH_TYPE_INVALID")
        rejection = paths["ZONE_REJECTION"]
        absorption = paths["ZONE_ABSORPTION_BREAK"]
        false_break = paths["FALSE_BREAK_REVERSION"]
        no_effect = paths["ZONE_NO_EFFECT_OTHER"]
        assert rejection is not None
        assert absorption is not None
        assert false_break is not None
        assert no_effect is not None
        if (
            len({path["scope"] for path in paths.values() if path is not None}) != 1
            or rejection["scope"] != zone["instrument"]
            or len(
                {
                    path["horizon_seconds"]
                    for path in paths.values()
                    if path is not None
                }
            )
            != 1
            or len(
                {
                    tuple(path["regime_scope"])
                    for path in paths.values()
                    if path is not None
                }
            )
            != 1
        ):
            raise V32DynamicResearchError("V32_ZONE_PATH_COMPARABILITY_INVALID")
        if (
            {rejection["direction"], absorption["direction"]} != {"LONG", "SHORT"}
            or false_break["direction"] != rejection["direction"]
            or no_effect["direction"] != "OTHER"
        ):
            raise V32DynamicResearchError("V32_ZONE_PATH_DIRECTION_INVALID")
        rejection_id = rejection["hypothesis_id"]
        absorption_id = absorption["hypothesis_id"]
        if (
            absorption_id not in rejection["opposition_ids"]
            or rejection_id not in absorption["opposition_ids"]
        ):
            raise V32DynamicResearchError("V32_ZONE_PATH_OPPOSITION_INVALID")
        zone_path_ids = set(zone["path_hypothesis_ids"].values())
        for modifier_id in zone["path_modifier_ids"]:
            modifier = modifier_map.get(modifier_id)
            if (
                modifier is None
                or zone_id not in modifier["affected_zone_ids"]
                or not set(zone["dependency_groups"]).intersection(
                    modifier["dependency_groups"]
                )
                or not zone_path_ids.intersection(
                    modifier["affected_hypothesis_ids"]
                )
            ):
                raise V32DynamicResearchError(
                    "V32_ZONE_PATH_MODIFIER_BINDING_INVALID"
                )

    normalized_clusters = [
        _cluster(row, hypotheses=hypothesis_map) for row in dependency_clusters
    ]
    cluster_ids = [row["cluster_id"] for row in normalized_clusters]
    if len(cluster_ids) != len(set(cluster_ids)):
        raise V32DynamicResearchError("V32_CLUSTER_ID_DUPLICATE")
    clustered_ids = [
        member
        for cluster in normalized_clusters
        for member in cluster["member_hypothesis_ids"]
    ]
    if set(clustered_ids) != non_residual_ids or len(clustered_ids) != len(
        set(clustered_ids)
    ):
        raise V32DynamicResearchError("V32_CLUSTER_COVERAGE_INVALID")
    for index, left in enumerate(normalized_clusters):
        left_dependencies = set().union(
            *(
                set(hypothesis_map[member]["dependency_groups"])
                for member in left["member_hypothesis_ids"]
            )
        )
        for right in normalized_clusters[index + 1 :]:
            if left["direction"] != right["direction"]:
                continue
            right_dependencies = set().union(
                *(
                    set(hypothesis_map[member]["dependency_groups"])
                    for member in right["member_hypothesis_ids"]
                )
            )
            if left_dependencies & right_dependencies:
                raise V32DynamicResearchError(
                    "V32_SAME_DIRECTION_CLUSTER_DEPENDENCY_OVERLAP"
                )

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run,
        "cycle_index": cycle_index,
        "as_of": as_of_text,
        "frame_mode": frame_mode,
        "previous_state_digest": previous,
        "market_regime_state": normalized_regime,
        "unknowns": sorted(normalized_unknowns, key=lambda row: row["unknown_id"]),
        "zones": sorted(normalized_zones, key=lambda row: row["zone_id"]),
        "hypotheses": sorted(
            normalized_hypotheses, key=lambda row: row["hypothesis_id"]
        ),
        "path_modifiers": sorted(
            normalized_modifiers, key=lambda row: row["modifier_id"]
        ),
        "dependency_clusters": sorted(
            normalized_clusters, key=lambda row: row["cluster_id"]
        ),
        "required_hypothesis_types": list(HYPOTHESIS_TYPES),
        "opposing_direction_policy": (
            "SYMMETRIC_CANDIDATE_COMPLETENESS_ONLY_"
            "NO_ACTIONABILITY_OR_POSITIVE_WEIGHT_REQUIREMENT"
        ),
        "residual_policy": "EXACTLY_ONE_OTHER_AND_ONE_UNKNOWN",
        "subjective_tier_policy": (
            "EXTREME_UNCERTAINTY_LOW_HIGH_ORDINAL_ONLY_"
            "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM_"
            "NO_DIRECT_EXTREME_TO_HIGH_TRANSITION_"
            "TERMINAL_IS_EXTREME_UNCERTAINTY_ZERO_RISK"
        ),
        "expiry_policy": (
            "STABLE_LINEAGE_REVISION_PREDECESSOR_FINGERPRINT_CROSS_CYCLE_"
            "NEW_ID_RENEWAL_WITH_POSTDATING_EVIDENCE_AND_TERMINAL_TOMBSTONES_"
            "NO_AUTOMATIC_TIER_DECAY"
        ),
        "modifier_policy": (
            "TYPED_CONDITIONS_TRIGGER_RISK_PROTECTION_INVALIDATORS_"
            "BIDIRECTIONAL_ZONE_HYPOTHESIS_SCOPE_NO_GLOBAL_BROADCAST"
        ),
        "resource_limits": dict(DURABLE_OBJECT_LIMITS),
        "resource_policy": (
            "TOTAL_DURABLE_OBJECT_COUNTS_INCLUDE_TERMINAL_TOMBSTONES_"
            "HARD_FAIL_NO_TRUNCATION"
        ),
        "probability_claim": "NONE_UNCALIBRATED_SUBJECTIVE_SUPPORT_ONLY",
        "brier_ece_allowed": False,
        "expected_value_allowed": False,
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_dynamic_research_state_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _STATE_FIELDS:
        raise V32DynamicResearchError("V32_STATE_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = build_v32_dynamic_research_state_v1(
            run_id=document["run_id"],
            cycle_index=document["cycle_index"],
            as_of=document["as_of"],
            frame_mode=document["frame_mode"],
            previous_state_digest=document["previous_state_digest"],
            market_regime_state=document["market_regime_state"],
            unknowns=document["unknowns"],
            zones=document["zones"],
            hypotheses=document["hypotheses"],
            path_modifiers=document["path_modifiers"],
            dependency_clusters=document["dependency_clusters"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V32DynamicResearchError("V32_STATE_DOCUMENT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32DynamicResearchError("V32_STATE_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "DIGEST_FIELD",
    "DIRECTIONS",
    "DURABLE_OBJECT_LIMITS",
    "ACTIONABLE_HYPOTHESIS_STATUSES",
    "FRAME_MODES",
    "HYPOTHESIS_STATUSES",
    "HYPOTHESIS_TYPES",
    "MARKET_REGIME_STATES",
    "NON_DIRECTIONAL_MARKET_REGIMES",
    "REGIME_FEATURE_REQUIRED_COMBINATIONS",
    "REGIME_FEATURE_REQUIRED_OBSERVABLE_FAMILIES",
    "REGIME_FEATURE_STATES",
    "PATH_MODIFIER_EFFECTS",
    "PATH_MODIFIER_STATUSES",
    "PATH_MODIFIER_TYPES",
    "SCHEMA_ID",
    "SUBJECTIVE_PLAUSIBILITY_TIERS",
    "SUBJECTIVE_TIER_ORDER",
    "SUBJECTIVE_TIER_RISK_CAP_UNITS",
    "UNKNOWN_BEHAVIOR_EFFECT",
    "UNKNOWN_TYPES",
    "V32DynamicResearchError",
    "MODIFIER_AFFECTED_ACTION_KINDS",
    "MODIFIER_PROTECTION_EFFECTS",
    "MODIFIER_TRIGGER_EFFECTS",
    "ZONE_METHODS",
    "ZONE_PATH_ROLES",
    "ZONE_QUALITIES",
    "ZONE_ROLES",
    "build_v32_dynamic_research_state_v1",
    "verify_v32_dynamic_research_state_v1",
]
