"""Deterministic contracts for evolving market research state.

The Strategy Agent may propose novel semantic hypotheses, expectations, and
sentiment explanations.  This module owns admission, lifecycle transitions,
point-in-time checks, deduplication, and replayable digests.  It performs no IO
and grants no execution authority.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .contracts.canonical import (
    canonical_decimal,
    canonical_digest,
    self_digest,
    verify_self_digest,
)


class DynamicResearchError(ValueError):
    """A dynamic-research contract failed closed."""


_HEX_64 = re.compile(r"^[0-9a-f]{64}$")

MARKET_CATEGORIES = (
    "PRICE_AND_RETURNS",
    "TREND_VOLATILITY_AND_STRUCTURE",
    "VOLUME_AND_ACTIVE_FLOW",
    "ORDER_BOOK_AND_LIQUIDITY",
    "OPEN_INTEREST_AND_LEVERAGE",
    "FUNDING_BASIS_AND_POSITIONING",
    "LIQUIDATION",
    "CROSS_MARKET_AND_MACRO",
    "NEWS_EVENTS_AND_REACTION",
    "INSTRUMENT_AND_DATA_QUALITY",
)

SENTIMENT_AXES = (
    "PRICE_DIRECTIONAL_PRESSURE",
    "STRUCTURE_PERSISTENCE",
    "PARTICIPATION_AND_FLOW",
    "CROWDING_DIRECTION",
    "LEVERAGE_CHANGE",
    "LIQUIDITY_RESILIENCE",
    "VOLATILITY_STRESS",
    "CROSS_MARKET_RISK_APPETITE",
    "EVENT_REACTION",
    "TIMEFRAME_COHERENCE",
)

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

_LEGACY_TO_V31_SENTIMENT_AXIS = {
    "PRICE_DIRECTIONAL_PRESSURE": "PRICE_DIRECTIONAL_PRESSURE",
    "STRUCTURE_PERSISTENCE": "STRUCTURE_PERSISTENCE",
    "PARTICIPATION_AND_FLOW": "PARTICIPATION_AND_ACTIVE_FLOW",
    "CROWDING_DIRECTION": "CROWDING_DIRECTION",
    "LEVERAGE_CHANGE": "LEVERAGE_CHANGE",
    "LIQUIDITY_RESILIENCE": "LIQUIDITY_RESILIENCE",
    "VOLATILITY_STRESS": "VOLATILITY_AND_TAIL_STRESS",
    "EVENT_REACTION": "EVENT_AND_NARRATIVE_REACTION",
    "CROSS_MARKET_RISK_APPETITE": "CROSS_MARKET_RISK_APPETITE_AND_REGIME",
    "TIMEFRAME_COHERENCE": "TIMEFRAME_COHERENCE",
}

HYPOTHESIS_TYPES = frozenset({"PATH", "MECHANISM", "TRADE"})
HYPOTHESIS_BIASES = frozenset(
    {"LONG", "SHORT", "BIDIRECTIONAL", "NEUTRAL", "UNKNOWN"}
)
HYPOTHESIS_STATES = frozenset(
    {
        "CANDIDATE",
        "WATCH",
        "ACTIVE",
        "DORMANT",
        "SUPERSEDED",
        "INVALIDATED",
        "EXPIRED",
        "ARCHIVED",
    }
)
TERMINAL_HYPOTHESIS_STATES = frozenset(
    {"SUPERSEDED", "INVALIDATED", "EXPIRED", "ARCHIVED"}
)
HYPOTHESIS_OPERATIONS = frozenset(
    {
        "CREATE",
        "REVISE",
        "PROMOTE",
        "DEMOTE",
        "SPLIT",
        "MERGE",
        "SUPERSEDE",
        "INVALIDATE",
        "EXPIRE",
        "ARCHIVE",
        "RESTORE",
    }
)

EXPECTATION_STATUSES = frozenset(
    {"OPEN", "FULFILLED", "PARTIAL", "FALSIFIED", "EXPIRED", "CANCELLED"}
)
TERMINAL_EXPECTATION_STATUSES = frozenset(
    {"FULFILLED", "FALSIFIED", "EXPIRED", "CANCELLED"}
)
EXPECTATION_OPERATIONS = frozenset(
    {"CREATE", "REVISE", "UPDATE_RESULT", "CLOSE"}
)

_FACT_FIELDS = frozenset(
    {
        "fact_id",
        "kind",
        "category",
        "metric",
        "value",
        "unit",
        "symbol",
        "timeframe",
        "window",
        "source_ref",
        "raw_ref",
        "raw_sha256",
        "observed_at",
        "available_at",
        "quality",
        "coverage",
        "dependency_group",
        "lineage",
        "transform",
        "limitations",
        "missing_reason",
    }
)
_SENTIMENT_INPUT_FIELDS = frozenset(
    {
        "axis",
        "required_dependency_groups",
        "contributors",
        "timeframe_states",
        "agent_interpretation",
        "limitations",
        "next_discriminating_observation",
    }
)
_CONTRIBUTOR_FIELDS = frozenset(
    {"fact_id", "ordinal_contribution", "rule", "direction"}
)
_SENTIMENT_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "symbol",
        "as_of",
        "market_information_snapshot_digest",
        "dimensions",
        "operational_synthesis",
        "overall_numeric_score",
        "probability_status",
        "unknown_is_neutral",
        "external_execution_authority",
        "executable",
        "sentiment_state_digest",
    }
)
_SENTIMENT_DIMENSION_FIELDS = frozenset(
    {
        "axis",
        "ordinal_value",
        "state_label",
        "required_dependency_groups",
        "contributors",
        "supporting_count",
        "opposing_count",
        "neutral_count",
        "unknown_count",
        "required_group_count",
        "observed_group_count",
        "coverage_ratio",
        "coverage_label",
        "conflict_state",
        "timeframe_states",
        "agent_interpretation",
        "limitations",
        "next_discriminating_observation",
    }
)
_SENTIMENT_CHANGE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "symbol",
        "changed_at",
        "prior_sentiment_state_digest",
        "current_sentiment_state_digest",
        "change_kind",
        "axis_changes",
        "overall_numeric_score",
        "probability_status",
        "external_execution_authority",
        "executable",
        "sentiment_change_digest",
    }
)
_V31_SENTIMENT_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "symbol",
        "as_of",
        "legacy_sentiment_state_digest",
        "market_information_snapshot_digest",
        "pit_dataset_digest",
        "downstream_scope",
        "migration_status",
        "legacy_axis_map",
        "unmapped_axes",
        "dimensions",
        "operational_synthesis",
        "overall_numeric_score",
        "probability_status",
        "unknown_is_neutral",
        "external_execution_authority",
        "executable",
        "sentiment_state_digest",
    }
)
_V31_SENTIMENT_EVIDENCE_BINDING_FIELDS = frozenset(
    {
        "evidence_ref",
        "evidence_digest",
        "admissibility_level",
    }
)
_V31_SENTIMENT_EVIDENCE_FIELDS = frozenset(
    {
        "fact_id",
        "ordinal_contribution",
        "rule",
        "direction",
        "dependency_group",
        "market_fact_digest",
        "evidence_ref",
        "evidence_digest",
        "admissibility_level",
    }
)
_V31_SENTIMENT_DIMENSION_FIELDS = frozenset(
    {
        "axis",
        "ordinal_value",
        "state_label",
        "evidence",
        "alternative_explanations",
        "quality",
        "required_dependency_groups",
        "conflict_state",
        "coverage_ratio",
        "timeframe_states",
        "change",
        "next_discriminating_observation",
    }
)
_HYPOTHESIS_FIELDS = frozenset(
    {
        "hypothesis_id",
        "revision",
        "hypothesis_type",
        "directional_bias",
        "family_label",
        "deduplication_key",
        "state",
        "parent_hypothesis_ids",
        "supersedes_ids",
        "derived_from_expectation_ids",
        "created_at",
        "updated_at",
        "horizon",
        "timeframe_scope",
        "premises",
        "expected_sequence",
        "support_rules",
        "oppose_rules",
        "hard_falsifiers",
        "expiry",
        "trade_triggers",
        "forbidden_conditions",
        "active_evidence_ids",
        "active_evidence_bindings",
        "support_level",
        "limitations",
        "novelty_reason",
        "agent_rationale",
    }
)
_HYPOTHESIS_DELTA_FIELDS = frozenset(
    {
        "delta_id",
        "operation",
        "occurred_at",
        "target_hypothesis_ids",
        "replacement_hypotheses",
        "evidence_ids",
        "evidence_bindings",
        "matched_hard_falsifier",
        "agent_rationale",
    }
)
_EXPECTATION_FIELDS = frozenset(
    {
        "expectation_id",
        "revision",
        "hypothesis_id",
        "parent_expectation_id",
        "deduplication_key",
        "created_at",
        "updated_at",
        "observation_start",
        "observation_deadline",
        "if_conditions",
        "expected_observations",
        "falsifying_observations",
        "evidence_sufficiency",
        "status",
        "result_evidence_refs",
        "result_evidence_bindings",
        "closed_at",
        "result_note",
    }
)
_EXPECTATION_OBSERVATION_FIELDS = frozenset(
    {"metric", "direction_or_range", "timeframe", "source_requirement"}
)
_EXPECTATION_DELTA_FIELDS = frozenset(
    {
        "delta_id",
        "operation",
        "occurred_at",
        "target_expectation_id",
        "expectation",
        "agent_rationale",
    }
)


def _timestamp(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DynamicResearchError(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DynamicResearchError(code) from exc
    if parsed.tzinfo is None:
        raise DynamicResearchError(code)
    return parsed.astimezone(UTC)


def _decimal(value: Any, code: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise DynamicResearchError(code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DynamicResearchError(code) from exc
    if not result.is_finite():
        raise DynamicResearchError(code)
    return result


def _strings(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise DynamicResearchError(code)
    rows = tuple(value)
    if (
        (not allow_empty and not rows)
        or any(not isinstance(item, str) or not item.strip() for item in rows)
        or len(rows) != len(set(rows))
    ):
        raise DynamicResearchError(code)
    return rows


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DynamicResearchError(code)
    return value.strip()


def _verify_digest(document: Mapping[str, Any], field: str, code: str) -> str:
    try:
        return verify_self_digest(document, field)
    except ValueError as exc:
        raise DynamicResearchError(code) from exc


def build_market_information_snapshot(
    *,
    run_id: str,
    cycle_index: int,
    symbol: str,
    as_of: str,
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Admit a point-in-time market snapshot without converting missing data to zero."""

    cutoff = _timestamp(as_of, "MARKET_SNAPSHOT_TIME_INVALID")
    if not run_id or cycle_index < 1 or not symbol or not facts:
        raise DynamicResearchError("MARKET_SNAPSHOT_IDENTITY_INVALID")
    normalized: list[dict[str, Any]] = []
    fact_ids: set[str] = set()
    category_counts = {category: 0 for category in MARKET_CATEGORIES}
    category_observed = {category: 0 for category in MARKET_CATEGORIES}
    for raw in facts:
        if not isinstance(raw, Mapping) or set(raw) != _FACT_FIELDS:
            raise DynamicResearchError("MARKET_FACT_SCHEMA_INVALID")
        fact_id = _text(raw.get("fact_id"), "MARKET_FACT_ID_INVALID")
        category = str(raw.get("category") or "")
        kind = str(raw.get("kind") or "")
        quality = str(raw.get("quality") or "")
        observed = _timestamp(raw.get("observed_at"), "MARKET_FACT_TIME_INVALID")
        available = _timestamp(raw.get("available_at"), "MARKET_FACT_TIME_INVALID")
        if (
            fact_id in fact_ids
            or category not in MARKET_CATEGORIES
            or kind not in {"RAW_FACT", "DERIVED_FEATURE"}
            or quality not in {"GOOD", "DEGRADED", "STALE", "UNKNOWN"}
            or observed > available
            or available > cutoff
            or str(raw.get("symbol") or "") != symbol
        ):
            raise DynamicResearchError("MARKET_FACT_INVALID")
        coverage = _decimal(raw.get("coverage"), "MARKET_FACT_COVERAGE_INVALID")
        if coverage < 0 or coverage > 1:
            raise DynamicResearchError("MARKET_FACT_COVERAGE_INVALID")
        value = raw.get("value")
        missing_reason = raw.get("missing_reason")
        raw_sha = raw.get("raw_sha256")
        if value is None:
            if quality != "UNKNOWN" or not isinstance(missing_reason, str) or not missing_reason:
                raise DynamicResearchError("MARKET_FACT_UNKNOWN_SEMANTICS_INVALID")
            if coverage != 0 or raw_sha is not None:
                raise DynamicResearchError("MARKET_FACT_UNKNOWN_SEMANTICS_INVALID")
        else:
            if missing_reason is not None or not isinstance(raw_sha, str) or _HEX_64.fullmatch(raw_sha) is None:
                raise DynamicResearchError("MARKET_FACT_OBSERVED_SEMANTICS_INVALID")
        transform = raw.get("transform")
        lineage = _strings(raw.get("lineage"), "MARKET_FACT_LINEAGE_INVALID", allow_empty=kind == "RAW_FACT")
        if kind == "RAW_FACT" and transform is not None:
            raise DynamicResearchError("MARKET_RAW_FACT_TRANSFORM_FORBIDDEN")
        if kind == "RAW_FACT" and lineage:
            raise DynamicResearchError("MARKET_RAW_FACT_LINEAGE_FORBIDDEN")
        if kind == "DERIVED_FEATURE" and (not isinstance(transform, str) or not transform.strip() or not lineage):
            raise DynamicResearchError("MARKET_DERIVED_LINEAGE_REQUIRED")
        for field in (
            "metric",
            "unit",
            "timeframe",
            "window",
            "source_ref",
            "raw_ref",
            "dependency_group",
            "limitations",
        ):
            _text(raw.get(field), "MARKET_FACT_TEXT_FIELD_INVALID")
        normalized.append(
            {
                **dict(raw),
                "fact_id": fact_id,
                "coverage": canonical_decimal(coverage),
                "lineage": list(lineage),
                "transform": None if transform is None else transform.strip(),
            }
        )
        fact_ids.add(fact_id)
        category_counts[category] += 1
        category_observed[category] += value is not None
    admitted_fact_ids = {row["fact_id"] for row in normalized}
    if any(
        row["kind"] == "DERIVED_FEATURE"
        and (
            row["fact_id"] in row["lineage"]
            or not set(row["lineage"]).issubset(admitted_fact_ids)
        )
        for row in normalized
    ):
        raise DynamicResearchError("MARKET_DERIVED_LINEAGE_UNKNOWN")
    missing_categories = [
        category for category in MARKET_CATEGORIES if category_counts[category] == 0
    ]
    if missing_categories:
        raise DynamicResearchError(
            "MARKET_SNAPSHOT_CATEGORY_MISSING:" + ",".join(missing_categories)
        )
    category_status = {
        category: {
            "fact_count": category_counts[category],
            "observed_count": category_observed[category],
            "unknown_count": category_counts[category] - category_observed[category],
            "status": (
                "UNKNOWN"
                if category_observed[category] == 0
                else "PARTIAL"
                if category_observed[category] < category_counts[category]
                else "OBSERVED"
            ),
        }
        for category in MARKET_CATEGORIES
    }
    snapshot = {
        "schema_id": "market_information_snapshot",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "cycle_index": cycle_index,
        "symbol": symbol,
        "as_of": as_of,
        "facts": sorted(normalized, key=lambda row: row["fact_id"]),
        "category_status": category_status,
        "missing_values_are_zero": False,
        "probability_status": "NO_UNCALIBRATED_PROBABILITY",
    }
    return self_digest(snapshot, "market_information_snapshot_digest")


def build_sentiment_state(
    *,
    market_snapshot: Mapping[str, Any],
    dimension_inputs: Sequence[Mapping[str, Any]],
    operational_synthesis: str,
) -> dict[str, Any]:
    """Build a replayable ten-axis ordinal vector with coverage and dissent."""

    snapshot_digest = _verify_digest(
        market_snapshot,
        "market_information_snapshot_digest",
        "SENTIMENT_MARKET_SNAPSHOT_DIGEST_INVALID",
    )
    if len(dimension_inputs) != len(SENTIMENT_AXES):
        raise DynamicResearchError("SENTIMENT_AXIS_COVERAGE_INCOMPLETE")
    facts = {row["fact_id"]: row for row in market_snapshot.get("facts", [])}
    axes_seen: set[str] = set()
    dimensions: list[dict[str, Any]] = []
    for raw in dimension_inputs:
        if not isinstance(raw, Mapping) or set(raw) != _SENTIMENT_INPUT_FIELDS:
            raise DynamicResearchError("SENTIMENT_DIMENSION_SCHEMA_INVALID")
        axis = str(raw.get("axis") or "")
        required_groups = _strings(
            raw.get("required_dependency_groups"),
            "SENTIMENT_REQUIRED_GROUPS_INVALID",
        )
        if axis not in SENTIMENT_AXES or axis in axes_seen:
            raise DynamicResearchError("SENTIMENT_AXIS_INVALID")
        contributors_raw = raw.get("contributors")
        if not isinstance(contributors_raw, (list, tuple)):
            raise DynamicResearchError("SENTIMENT_CONTRIBUTORS_INVALID")
        contributors: list[dict[str, Any]] = []
        contributor_groups: set[str] = set()
        values: list[int] = []
        for contributor in contributors_raw:
            if not isinstance(contributor, Mapping) or set(contributor) != _CONTRIBUTOR_FIELDS:
                raise DynamicResearchError("SENTIMENT_CONTRIBUTOR_SCHEMA_INVALID")
            fact_id = str(contributor.get("fact_id") or "")
            fact = facts.get(fact_id)
            value = contributor.get("ordinal_contribution")
            if (
                fact is None
                or fact.get("value") is None
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value not in {-2, -1, 0, 1, 2}
                or not str(contributor.get("rule") or "").strip()
                or contributor.get("direction") not in {"NEGATIVE", "NEUTRAL", "POSITIVE"}
            ):
                raise DynamicResearchError("SENTIMENT_CONTRIBUTOR_INVALID")
            expected_direction = "NEGATIVE" if value < 0 else "POSITIVE" if value > 0 else "NEUTRAL"
            if contributor["direction"] != expected_direction:
                raise DynamicResearchError("SENTIMENT_CONTRIBUTOR_DIRECTION_INVALID")
            dependency_group = fact["dependency_group"]
            if dependency_group in contributor_groups or dependency_group not in required_groups:
                raise DynamicResearchError("SENTIMENT_DEPENDENCY_GROUP_DUPLICATE_OR_UNREGISTERED")
            contributor_groups.add(dependency_group)
            contributors.append(dict(contributor))
            contributors[-1]["dependency_group"] = dependency_group
            values.append(value)
        observed_groups = len(contributor_groups)
        coverage = Decimal(observed_groups) / Decimal(len(required_groups))
        unknown_count = len(required_groups) - observed_groups
        if coverage < Decimal("0.5") or not values:
            ordinal_value: int | None = None
            state_label = "UNKNOWN_INSUFFICIENT_COVERAGE"
            conflict = "UNKNOWN"
        else:
            signs = {value > 0 for value in values if value != 0}
            conflict = (
                "CONTRADICTORY"
                if len(signs) > 1
                else "ALIGNED"
                if signs
                else "MIXED"
            )
            if axis == "TIMEFRAME_COHERENCE":
                if conflict == "CONTRADICTORY":
                    ordinal_value = 0
                elif not signs:
                    ordinal_value = 0
                elif signs == {True}:
                    ordinal_value = (
                        2
                        if coverage == Decimal("1")
                        and all(value > 0 for value in values)
                        else 1
                    )
                else:
                    ordinal_value = (
                        -2
                        if coverage == Decimal("1")
                        and all(value < 0 for value in values)
                        else -1
                    )
            else:
                balance = sum(values)
                ordinal_value = max(
                    -1 if conflict == "CONTRADICTORY" else -2,
                    min(1 if conflict == "CONTRADICTORY" else 2, balance),
                )
            state_label = {
                -2: "STRONG_NEGATIVE_AXIS_STATE",
                -1: "NEGATIVE_AXIS_STATE",
                0: "BALANCED_OR_MIXED_AXIS_STATE",
                1: "POSITIVE_AXIS_STATE",
                2: "STRONG_POSITIVE_AXIS_STATE",
            }[ordinal_value]
        timeframe_states = raw.get("timeframe_states")
        if not isinstance(timeframe_states, Mapping) or any(
            not isinstance(key, str)
            or not key
            or (value is not None and (isinstance(value, bool) or value not in {-2, -1, 0, 1, 2}))
            for key, value in timeframe_states.items()
        ):
            raise DynamicResearchError("SENTIMENT_TIMEFRAME_STATE_INVALID")
        dimensions.append(
            {
                "axis": axis,
                "ordinal_value": ordinal_value,
                "state_label": state_label,
                "required_dependency_groups": list(required_groups),
                "contributors": sorted(contributors, key=lambda row: row["fact_id"]),
                "supporting_count": sum(value > 0 for value in values),
                "opposing_count": sum(value < 0 for value in values),
                "neutral_count": sum(value == 0 for value in values),
                "unknown_count": unknown_count,
                "required_group_count": len(required_groups),
                "observed_group_count": observed_groups,
                "coverage_ratio": canonical_decimal(coverage),
                "coverage_label": (
                    "HIGH" if coverage >= Decimal("0.8") else "MEDIUM" if coverage >= Decimal("0.5") else "LOW"
                ),
                "conflict_state": conflict,
                "timeframe_states": dict(sorted(timeframe_states.items())),
                "agent_interpretation": _text(raw.get("agent_interpretation"), "SENTIMENT_INTERPRETATION_INVALID"),
                "limitations": _text(raw.get("limitations"), "SENTIMENT_LIMITATIONS_INVALID"),
                "next_discriminating_observation": _text(
                    raw.get("next_discriminating_observation"),
                    "SENTIMENT_NEXT_OBSERVATION_INVALID",
                ),
            }
        )
        axes_seen.add(axis)
    if axes_seen != set(SENTIMENT_AXES):
        raise DynamicResearchError("SENTIMENT_AXIS_COVERAGE_INCOMPLETE")
    state = {
        "schema_id": "multidimensional_market_sentiment_state",
        "schema_version": "1.0.0",
        "run_id": market_snapshot["run_id"],
        "cycle_index": market_snapshot["cycle_index"],
        "symbol": market_snapshot["symbol"],
        "as_of": market_snapshot["as_of"],
        "market_information_snapshot_digest": snapshot_digest,
        "dimensions": sorted(dimensions, key=lambda row: SENTIMENT_AXES.index(row["axis"])),
        "operational_synthesis": _text(operational_synthesis, "SENTIMENT_SYNTHESIS_INVALID"),
        "overall_numeric_score": None,
        "probability_status": "ORDINAL_VECTOR_NOT_PROBABILITY",
        "unknown_is_neutral": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(state, "sentiment_state_digest")


def migrate_legacy_sentiment_state_to_v31(
    *,
    legacy_sentiment_state: Mapping[str, Any],
    market_information_snapshot: Mapping[str, Any],
    pit_dataset_digest: str,
    sentiment_evidence_bindings: Mapping[str, Mapping[str, str]],
    downstream_scope: str,
    previous_v31_sentiment_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map legacy axes while binding every contributor to admitted PIT data.

    This migration is deliberately not a source-admission boundary.  It seals
    the caller-supplied exact bindings into the V3.1 state; the application
    cycle must compare them with its independently verified PIT catalog.
    """

    legacy_digest = verify_sentiment_state(legacy_sentiment_state)
    if legacy_sentiment_state.get("schema_id") != "multidimensional_market_sentiment_state":
        raise DynamicResearchError("SENTIMENT_LEGACY_STATE_REQUIRED")
    snapshot_digest = _verify_digest(
        market_information_snapshot,
        "market_information_snapshot_digest",
        "SENTIMENT_MARKET_SNAPSHOT_DIGEST_INVALID",
    )
    if (
        snapshot_digest
        != legacy_sentiment_state["market_information_snapshot_digest"]
    ):
        raise DynamicResearchError("SENTIMENT_MARKET_SNAPSHOT_BINDING_INVALID")
    if not isinstance(pit_dataset_digest, str) or _HEX_64.fullmatch(
        pit_dataset_digest
    ) is None:
        raise DynamicResearchError("SENTIMENT_PIT_DATASET_DIGEST_INVALID")
    if downstream_scope not in {"HYPOTHESIS_ONLY", "PATH_ACTION"}:
        raise DynamicResearchError("SENTIMENT_DOWNSTREAM_SCOPE_INVALID")
    if not isinstance(sentiment_evidence_bindings, Mapping):
        raise DynamicResearchError("SENTIMENT_EVIDENCE_BINDINGS_INVALID")
    contributor_fact_ids = {
        str(contributor["fact_id"])
        for dimension in legacy_sentiment_state["dimensions"]
        for contributor in dimension["contributors"]
    }
    if set(sentiment_evidence_bindings) != contributor_fact_ids:
        raise DynamicResearchError("SENTIMENT_EVIDENCE_BINDINGS_INCOMPLETE")
    normalized_evidence_bindings: dict[str, dict[str, str]] = {}
    for fact_id in sorted(contributor_fact_ids):
        raw_binding = sentiment_evidence_bindings[fact_id]
        if (
            not isinstance(raw_binding, Mapping)
            or set(raw_binding) != _V31_SENTIMENT_EVIDENCE_BINDING_FIELDS
        ):
            raise DynamicResearchError("SENTIMENT_EVIDENCE_BINDING_INVALID")
        evidence_ref = _text(
            raw_binding.get("evidence_ref"),
            "SENTIMENT_EVIDENCE_BINDING_INVALID",
        )
        evidence_digest = raw_binding.get("evidence_digest")
        admissibility_level = raw_binding.get("admissibility_level")
        if (
            not isinstance(evidence_digest, str)
            or _HEX_64.fullmatch(evidence_digest) is None
            or admissibility_level
            not in {"HYPOTHESIS_ADMISSIBLE", "INFERENCE_ADMISSIBLE"}
            or (
                downstream_scope == "PATH_ACTION"
                and admissibility_level != "INFERENCE_ADMISSIBLE"
            )
        ):
            raise DynamicResearchError("SENTIMENT_EVIDENCE_BINDING_INVALID")
        normalized_evidence_bindings[fact_id] = {
            "evidence_ref": evidence_ref,
            "evidence_digest": evidence_digest,
            "admissibility_level": str(admissibility_level),
        }
    snapshot_facts = {
        str(row["fact_id"]): row
        for row in market_information_snapshot.get("facts", ())
        if isinstance(row, Mapping) and isinstance(row.get("fact_id"), str)
    }
    if not contributor_fact_ids.issubset(snapshot_facts):
        raise DynamicResearchError("SENTIMENT_CONTRIBUTOR_FACT_MISSING")
    previous_by_axis: dict[str, Mapping[str, Any]] = {}
    if previous_v31_sentiment_state is not None:
        verify_sentiment_state(previous_v31_sentiment_state)
        if (
            previous_v31_sentiment_state.get("schema_id")
            != "theory_paper_v2_v31_multidimensional_market_sentiment_state"
            or legacy_sentiment_state["cycle_index"]
            != previous_v31_sentiment_state["cycle_index"] + 1
            or legacy_sentiment_state["run_id"]
            != previous_v31_sentiment_state["run_id"]
            or legacy_sentiment_state["symbol"]
            != previous_v31_sentiment_state["symbol"]
            or previous_v31_sentiment_state.get("downstream_scope")
            != downstream_scope
        ):
            raise DynamicResearchError("SENTIMENT_V31_PREDECESSOR_INVALID")
        previous_by_axis = {
            row["axis"]: row
            for row in previous_v31_sentiment_state["dimensions"]
        }
    legacy_by_v31_axis = {
        _LEGACY_TO_V31_SENTIMENT_AXIS[row["axis"]]: row
        for row in legacy_sentiment_state["dimensions"]
    }
    dimensions: list[dict[str, Any]] = []
    for axis in V31_SENTIMENT_AXES:
        legacy = legacy_by_v31_axis.get(axis)
        previous = previous_by_axis.get(axis)
        if legacy is None:
            ordinal = None
            state_label = "UNKNOWN_UNMAPPED_LEGACY_AXIS"
            evidence: list[dict[str, Any]] = []
            required_groups: list[str] = []
            conflict = "UNKNOWN"
            coverage = "0"
            timeframes: dict[str, int | None] = {}
            quality = {
                "coverage_label": "LOW",
                "required_group_count": 0,
                "observed_group_count": 0,
                "unknown_count": 0,
                "conflict_state": "UNKNOWN",
                "migration_quality": "UNKNOWN_LEGACY_AXIS_NOT_RECORDED",
            }
            alternatives = ["UNKNOWN_LEGACY_ALTERNATIVES_NOT_RECORDED"]
            next_observation = (
                "Collect direct V3.1 evidence for this unmapped sentiment axis."
            )
        else:
            ordinal = legacy["ordinal_value"]
            state_label = legacy["state_label"]
            evidence = []
            for contributor in legacy["contributors"]:
                fact_id = str(contributor["fact_id"])
                evidence.append(
                    {
                        **dict(contributor),
                        "market_fact_digest": canonical_digest(
                            snapshot_facts[fact_id]
                        ),
                        **normalized_evidence_bindings[fact_id],
                    }
                )
            required_groups = list(legacy["required_dependency_groups"])
            conflict = legacy["conflict_state"]
            coverage = legacy["coverage_ratio"]
            timeframes = dict(legacy["timeframe_states"])
            quality = {
                "coverage_label": legacy["coverage_label"],
                "required_group_count": legacy["required_group_count"],
                "observed_group_count": legacy["observed_group_count"],
                "unknown_count": legacy["unknown_count"],
                "conflict_state": conflict,
                "migration_quality": "LEGACY_V1_EXACT_AXIS_MAPPING",
            }
            alternatives = [
                "UNKNOWN_LEGACY_ALTERNATIVES_NOT_RECORDED",
                legacy["limitations"],
            ]
            next_observation = legacy["next_discriminating_observation"]
        prior_ordinal = None if previous is None else previous["ordinal_value"]
        if previous is None:
            change_label = "UNKNOWN_NO_PRIOR_V31_STATE"
            ordinal_delta = None
        elif prior_ordinal is None and ordinal is None:
            change_label = "UNKNOWN_UNCHANGED"
            ordinal_delta = None
        elif prior_ordinal is None:
            change_label = "RESOLVED_FROM_UNKNOWN"
            ordinal_delta = None
        elif ordinal is None:
            change_label = "BECAME_UNKNOWN"
            ordinal_delta = None
        else:
            ordinal_delta = ordinal - prior_ordinal
            change_label = (
                "UNCHANGED"
                if ordinal_delta == 0
                else "MOVED_POSITIVE"
                if ordinal_delta > 0
                else "MOVED_NEGATIVE"
            )
        dimensions.append(
            {
                "axis": axis,
                "ordinal_value": ordinal,
                "state_label": state_label,
                "evidence": evidence,
                "alternative_explanations": alternatives,
                "quality": quality,
                "required_dependency_groups": required_groups,
                "conflict_state": conflict,
                "coverage_ratio": coverage,
                "timeframe_states": timeframes,
                "change": {
                    "prior_ordinal_value": prior_ordinal,
                    "ordinal_delta": ordinal_delta,
                    "change_label": change_label,
                },
                "next_discriminating_observation": next_observation,
            }
        )
    document = {
        "schema_id": "theory_paper_v2_v31_multidimensional_market_sentiment_state",
        "schema_version": "3.1.0",
        "run_id": legacy_sentiment_state["run_id"],
        "cycle_index": legacy_sentiment_state["cycle_index"],
        "symbol": legacy_sentiment_state["symbol"],
        "as_of": legacy_sentiment_state["as_of"],
        "legacy_sentiment_state_digest": legacy_digest,
        "market_information_snapshot_digest": snapshot_digest,
        "pit_dataset_digest": pit_dataset_digest,
        "downstream_scope": downstream_scope,
        "migration_status": "LEGACY_V1_INPUT_MAPPED_TO_V31",
        "legacy_axis_map": dict(sorted(_LEGACY_TO_V31_SENTIMENT_AXIS.items())),
        "unmapped_axes": [
            axis for axis in V31_SENTIMENT_AXES if axis not in legacy_by_v31_axis
        ],
        "dimensions": dimensions,
        "operational_synthesis": legacy_sentiment_state[
            "operational_synthesis"
        ],
        "overall_numeric_score": None,
        "probability_status": "ORDINAL_VECTOR_NOT_PROBABILITY",
        "unknown_is_neutral": False,
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "sentiment_state_digest")


def verify_sentiment_state(document: Mapping[str, Any]) -> str:
    """Verify a complete ten-axis ordinal state without inventing a total."""

    if isinstance(document, Mapping) and document.get("schema_id") == (
        "theory_paper_v2_v31_multidimensional_market_sentiment_state"
    ):
        return _verify_v31_sentiment_state(document)

    if (
        not isinstance(document, Mapping)
        or set(document) != _SENTIMENT_STATE_FIELDS
        or document.get("schema_id") != "multidimensional_market_sentiment_state"
        or document.get("schema_version") != "1.0.0"
        or document.get("overall_numeric_score") is not None
        or document.get("probability_status") != "ORDINAL_VECTOR_NOT_PROBABILITY"
        or document.get("unknown_is_neutral") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or isinstance(document.get("cycle_index"), bool)
        or not isinstance(document.get("cycle_index"), int)
        or document["cycle_index"] < 1
    ):
        raise DynamicResearchError("SENTIMENT_STATE_SCHEMA_INVALID")
    _text(document.get("run_id"), "SENTIMENT_RUN_ID_INVALID")
    _text(document.get("symbol"), "SENTIMENT_SYMBOL_INVALID")
    _timestamp(document.get("as_of"), "SENTIMENT_TIME_INVALID")
    _digest_value = document.get("market_information_snapshot_digest")
    if not isinstance(_digest_value, str) or _HEX_64.fullmatch(_digest_value) is None:
        raise DynamicResearchError("SENTIMENT_MARKET_SNAPSHOT_DIGEST_INVALID")
    dimensions = document.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != len(SENTIMENT_AXES):
        raise DynamicResearchError("SENTIMENT_AXIS_COVERAGE_INCOMPLETE")
    for expected_axis, row in zip(SENTIMENT_AXES, dimensions):
        if (
            not isinstance(row, Mapping)
            or set(row) != _SENTIMENT_DIMENSION_FIELDS
            or row.get("axis") != expected_axis
            or not isinstance(row.get("required_dependency_groups"), list)
            or row["required_dependency_groups"]
            != sorted(row["required_dependency_groups"])
            or len(row["required_dependency_groups"])
            != len(set(row["required_dependency_groups"]))
            or row.get("required_group_count")
            != len(row["required_dependency_groups"])
            or not isinstance(row.get("contributors"), list)
            or row.get("observed_group_count") != len(row["contributors"])
            or row.get("unknown_count")
            != row.get("required_group_count", 0) - row.get("observed_group_count", 0)
            or row.get("conflict_state")
            not in {"UNKNOWN", "CONTRADICTORY", "ALIGNED", "MIXED"}
        ):
            raise DynamicResearchError("SENTIMENT_DIMENSION_STATE_INVALID")
        contributor_groups = [item.get("dependency_group") for item in row["contributors"]]
        if (
            len(contributor_groups) != len(set(contributor_groups))
            or not set(contributor_groups).issubset(
                set(row["required_dependency_groups"])
            )
        ):
            raise DynamicResearchError("SENTIMENT_DEPENDENCY_BINDING_INVALID")
        ordinal = row.get("ordinal_value")
        if ordinal is not None and (
            isinstance(ordinal, bool) or ordinal not in {-2, -1, 0, 1, 2}
        ):
            raise DynamicResearchError("SENTIMENT_ORDINAL_INVALID")
        if ordinal is None and (
            row.get("state_label") != "UNKNOWN_INSUFFICIENT_COVERAGE"
            or row.get("conflict_state") != "UNKNOWN"
        ):
            raise DynamicResearchError("SENTIMENT_UNKNOWN_SEMANTICS_INVALID")
    try:
        return verify_self_digest(document, "sentiment_state_digest")
    except ValueError as exc:
        raise DynamicResearchError("SENTIMENT_STATE_DIGEST_INVALID") from exc


def _verify_v31_sentiment_state(document: Mapping[str, Any]) -> str:
    if (
        set(document) != _V31_SENTIMENT_STATE_FIELDS
        or document.get("schema_id")
        != "theory_paper_v2_v31_multidimensional_market_sentiment_state"
        or document.get("schema_version") != "3.1.0"
        or document.get("migration_status")
        != "LEGACY_V1_INPUT_MAPPED_TO_V31"
        or document.get("overall_numeric_score") is not None
        or document.get("probability_status") != "ORDINAL_VECTOR_NOT_PROBABILITY"
        or document.get("unknown_is_neutral") is not False
        or document.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or document.get("executable") is not False
        or document.get("legacy_axis_map")
        != dict(sorted(_LEGACY_TO_V31_SENTIMENT_AXIS.items()))
        or document.get("downstream_scope")
        not in {"HYPOTHESIS_ONLY", "PATH_ACTION"}
        or isinstance(document.get("cycle_index"), bool)
        or not isinstance(document.get("cycle_index"), int)
        or document["cycle_index"] < 1
    ):
        raise DynamicResearchError("SENTIMENT_V31_SCHEMA_INVALID")
    _text(document.get("run_id"), "SENTIMENT_RUN_ID_INVALID")
    _text(document.get("symbol"), "SENTIMENT_SYMBOL_INVALID")
    _timestamp(document.get("as_of"), "SENTIMENT_TIME_INVALID")
    _text(
        document.get("operational_synthesis"),
        "SENTIMENT_SYNTHESIS_INVALID",
    )
    dimensions = document.get("dimensions")
    if (
        not isinstance(dimensions, list)
        or [row.get("axis") for row in dimensions if isinstance(row, Mapping)]
        != list(V31_SENTIMENT_AXES)
        or document.get("unmapped_axes")
        != [
            "FORCED_DELEVERAGING_PRESSURE",
            "ATTENTION_AND_AUDIENCE_RESPONSE",
        ]
    ):
        raise DynamicResearchError("SENTIMENT_V31_AXIS_COVERAGE_INVALID")
    for row in dimensions:
        if (
            not isinstance(row, Mapping)
            or set(row) != _V31_SENTIMENT_DIMENSION_FIELDS
            or not isinstance(row.get("evidence"), list)
            or not isinstance(row.get("alternative_explanations"), list)
            or not row["alternative_explanations"]
            or not isinstance(row.get("quality"), Mapping)
            or not isinstance(row.get("timeframe_states"), Mapping)
            or not isinstance(row.get("change"), Mapping)
            or not str(row.get("next_discriminating_observation") or "").strip()
        ):
            raise DynamicResearchError("SENTIMENT_V31_DIMENSION_INVALID")
        ordinal = row.get("ordinal_value")
        if ordinal is not None and (
            isinstance(ordinal, bool) or ordinal not in {-2, -1, 0, 1, 2}
        ):
            raise DynamicResearchError("SENTIMENT_ORDINAL_INVALID")
        required_groups = row.get("required_dependency_groups")
        if (
            not isinstance(required_groups, list)
            or len(required_groups) != len(set(required_groups))
            or any(
                not isinstance(group, str) or not group.strip()
                for group in required_groups
            )
            or row.get("conflict_state")
            not in {"UNKNOWN", "CONTRADICTORY", "ALIGNED", "MIXED"}
        ):
            raise DynamicResearchError("SENTIMENT_V31_DIMENSION_INVALID")
        coverage = _decimal(
            row.get("coverage_ratio"), "SENTIMENT_COVERAGE_INVALID"
        )
        if coverage < 0 or coverage > 1 or canonical_decimal(coverage) != row.get(
            "coverage_ratio"
        ):
            raise DynamicResearchError("SENTIMENT_COVERAGE_INVALID")
        dimension_fact_ids: set[str] = set()
        dimension_dependency_groups: set[str] = set()
        for evidence in row["evidence"]:
            if (
                not isinstance(evidence, Mapping)
                or set(evidence) != _V31_SENTIMENT_EVIDENCE_FIELDS
                or evidence.get("fact_id") in dimension_fact_ids
                or evidence.get("dependency_group")
                in dimension_dependency_groups
                or evidence.get("dependency_group") not in required_groups
                or not isinstance(evidence.get("market_fact_digest"), str)
                or _HEX_64.fullmatch(evidence["market_fact_digest"]) is None
                or not isinstance(evidence.get("evidence_digest"), str)
                or _HEX_64.fullmatch(evidence["evidence_digest"]) is None
                or evidence.get("admissibility_level")
                not in {"HYPOTHESIS_ADMISSIBLE", "INFERENCE_ADMISSIBLE"}
                or (
                    document["downstream_scope"] == "PATH_ACTION"
                    and evidence.get("admissibility_level")
                    != "INFERENCE_ADMISSIBLE"
                )
            ):
                raise DynamicResearchError("SENTIMENT_V31_EVIDENCE_INVALID")
            dimension_fact_ids.add(str(evidence["fact_id"]))
            dimension_dependency_groups.add(str(evidence["dependency_group"]))
        if row["axis"] in document["unmapped_axes"] and (
            row.get("ordinal_value") is not None
            or row.get("state_label") != "UNKNOWN_UNMAPPED_LEGACY_AXIS"
            or row.get("evidence")
            or row.get("conflict_state") != "UNKNOWN"
            or row.get("coverage_ratio") != "0"
        ):
            raise DynamicResearchError("SENTIMENT_V31_UNMAPPED_AXIS_NOT_UNKNOWN")
    for field in (
        "legacy_sentiment_state_digest",
        "market_information_snapshot_digest",
        "pit_dataset_digest",
    ):
        if (
            not isinstance(document.get(field), str)
            or _HEX_64.fullmatch(document[field]) is None
        ):
            raise DynamicResearchError("SENTIMENT_V31_BINDING_INVALID")
    try:
        return verify_self_digest(document, "sentiment_state_digest")
    except ValueError as exc:
        raise DynamicResearchError("SENTIMENT_STATE_DIGEST_INVALID") from exc


def build_sentiment_state_change(
    *,
    current_sentiment_state: Mapping[str, Any],
    changed_at: str,
    previous_sentiment_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind exact per-axis ordinal changes; never aggregate them to a total."""

    current_digest = verify_sentiment_state(current_sentiment_state)
    changed = _timestamp(changed_at, "SENTIMENT_CHANGE_TIME_INVALID")
    current_time = _timestamp(
        current_sentiment_state["as_of"], "SENTIMENT_TIME_INVALID"
    )
    if changed < current_time:
        raise DynamicResearchError("SENTIMENT_CHANGE_PRECEDES_STATE")
    previous_digest: str | None = None
    previous_dimensions: dict[str, Mapping[str, Any]] = {}
    if previous_sentiment_state is None:
        if current_sentiment_state["cycle_index"] != 1:
            raise DynamicResearchError("SENTIMENT_PREVIOUS_STATE_REQUIRED")
        change_kind = "GENESIS_ADMISSION"
    else:
        previous_digest = verify_sentiment_state(previous_sentiment_state)
        if (
            current_sentiment_state["cycle_index"]
            != previous_sentiment_state["cycle_index"] + 1
            or current_sentiment_state["run_id"] != previous_sentiment_state["run_id"]
            or current_sentiment_state["symbol"] != previous_sentiment_state["symbol"]
            or _timestamp(previous_sentiment_state["as_of"], "SENTIMENT_TIME_INVALID")
            >= current_time
        ):
            raise DynamicResearchError("SENTIMENT_PREVIOUS_STATE_INVALID")
        change_kind = "CYCLE_UPDATE"
        previous_dimensions = {
            row["axis"]: row for row in previous_sentiment_state["dimensions"]
        }
    axis_changes: list[dict[str, Any]] = []
    for current in current_sentiment_state["dimensions"]:
        prior = previous_dimensions.get(current["axis"])
        prior_value = None if prior is None else prior["ordinal_value"]
        current_value = current["ordinal_value"]
        if prior is None:
            label = "GENESIS"
            delta = None
        elif prior_value is None and current_value is None:
            label = "UNKNOWN_UNCHANGED"
            delta = None
        elif prior_value is None:
            label = "RESOLVED_FROM_UNKNOWN"
            delta = None
        elif current_value is None:
            label = "BECAME_UNKNOWN"
            delta = None
        else:
            delta = current_value - prior_value
            label = (
                "UNCHANGED"
                if delta == 0
                else "MOVED_POSITIVE"
                if delta > 0
                else "MOVED_NEGATIVE"
            )
        axis_changes.append(
            {
                "axis": current["axis"],
                "prior_ordinal_value": prior_value,
                "current_ordinal_value": current_value,
                "ordinal_delta": delta,
                "change_label": label,
                "prior_conflict_state": None if prior is None else prior["conflict_state"],
                "current_conflict_state": current["conflict_state"],
                "prior_coverage_ratio": None if prior is None else prior["coverage_ratio"],
                "current_coverage_ratio": current["coverage_ratio"],
                "timeframe_states_changed": (
                    None
                    if prior is None
                    else prior["timeframe_states"] != current["timeframe_states"]
                ),
                "dependency_groups_changed": (
                    None
                    if prior is None
                    else prior["required_dependency_groups"]
                    != current["required_dependency_groups"]
                ),
            }
        )
    document = {
        "schema_id": "multidimensional_market_sentiment_change",
        "schema_version": "1.0.0",
        "run_id": current_sentiment_state["run_id"],
        "cycle_index": current_sentiment_state["cycle_index"],
        "symbol": current_sentiment_state["symbol"],
        "changed_at": changed_at,
        "prior_sentiment_state_digest": previous_digest,
        "current_sentiment_state_digest": current_digest,
        "change_kind": change_kind,
        "axis_changes": axis_changes,
        "overall_numeric_score": None,
        "probability_status": "ORDINAL_CHANGE_VECTOR_NOT_PROBABILITY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(document, "sentiment_change_digest")


def verify_sentiment_state_change(
    document: Mapping[str, Any],
    *,
    current_sentiment_state: Mapping[str, Any],
    previous_sentiment_state: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(document, Mapping) or set(document) != _SENTIMENT_CHANGE_FIELDS:
        raise DynamicResearchError("SENTIMENT_CHANGE_SCHEMA_INVALID")
    rebuilt = build_sentiment_state_change(
        current_sentiment_state=current_sentiment_state,
        previous_sentiment_state=previous_sentiment_state,
        changed_at=document.get("changed_at"),
    )
    if rebuilt != dict(document):
        raise DynamicResearchError("SENTIMENT_CHANGE_REPLAY_MISMATCH")
    return rebuilt["sentiment_change_digest"]


def _normalize_hypothesis(raw: Mapping[str, Any], *, cutoff: datetime) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _HYPOTHESIS_FIELDS:
        raise DynamicResearchError("HYPOTHESIS_SCHEMA_INVALID")
    hypothesis_id = _text(raw.get("hypothesis_id"), "HYPOTHESIS_ID_INVALID")
    revision = raw.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise DynamicResearchError("HYPOTHESIS_REVISION_INVALID")
    created = _timestamp(raw.get("created_at"), "HYPOTHESIS_TIME_INVALID")
    updated = _timestamp(raw.get("updated_at"), "HYPOTHESIS_TIME_INVALID")
    expiry = _timestamp(raw.get("expiry"), "HYPOTHESIS_EXPIRY_INVALID")
    if created > updated or updated > cutoff or expiry <= created:
        raise DynamicResearchError("HYPOTHESIS_TIME_INVALID")
    if raw.get("hypothesis_type") not in HYPOTHESIS_TYPES or raw.get("directional_bias") not in HYPOTHESIS_BIASES or raw.get("state") not in HYPOTHESIS_STATES:
        raise DynamicResearchError("HYPOTHESIS_ENUM_INVALID")
    normalized = dict(raw)
    for field in (
        "family_label",
        "deduplication_key",
        "horizon",
        "support_level",
        "novelty_reason",
        "agent_rationale",
    ):
        normalized[field] = _text(raw.get(field), "HYPOTHESIS_TEXT_INVALID")
    for field in (
        "parent_hypothesis_ids",
        "supersedes_ids",
        "derived_from_expectation_ids",
        "timeframe_scope",
        "premises",
        "expected_sequence",
        "support_rules",
        "oppose_rules",
        "hard_falsifiers",
        "trade_triggers",
        "forbidden_conditions",
        "active_evidence_ids",
        "limitations",
    ):
        normalized[field] = list(
            _strings(
                raw.get(field),
                "HYPOTHESIS_LIST_INVALID",
                allow_empty=field
                in {
                    "parent_hypothesis_ids",
                    "supersedes_ids",
                    "derived_from_expectation_ids",
                    "trade_triggers",
                    "forbidden_conditions",
                    "active_evidence_ids",
                    "limitations",
                },
            )
        )
    normalized["hypothesis_id"] = hypothesis_id
    normalized["active_evidence_bindings"] = _normalize_evidence_bindings(
        raw.get("active_evidence_bindings"),
        refs=normalized["active_evidence_ids"],
        code="HYPOTHESIS_ACTIVE_EVIDENCE_BINDING_INVALID",
    )
    return normalized


def _normalize_evidence_bindings(
    value: Any, *, refs: Sequence[str], code: str
) -> dict[str, str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != set(refs)
        or any(
            not isinstance(ref, str)
            or not ref
            or not isinstance(digest, str)
            or _HEX_64.fullmatch(digest) is None
            for ref, digest in value.items()
        )
    ):
        raise DynamicResearchError(code)
    return dict(sorted(value.items()))


def _hypothesis_semantic_fingerprint(row: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "hypothesis_type": row["hypothesis_type"],
            "directional_bias": row["directional_bias"],
            "horizon": row["horizon"],
            "timeframe_scope": row["timeframe_scope"],
            "premises": row["premises"],
            "expected_sequence": row["expected_sequence"],
            "support_rules": row["support_rules"],
            "oppose_rules": row["oppose_rules"],
            "hard_falsifiers": row["hard_falsifiers"],
            "trade_triggers": row["trade_triggers"],
            "forbidden_conditions": row["forbidden_conditions"],
        }
    )


def _assert_hypothesis_parent_graph_acyclic(
    hypotheses: Mapping[str, Mapping[str, Any]],
) -> None:
    """Require hypothesis lineage to be an existing-node DAG."""

    graph: dict[str, tuple[str, ...]] = {}
    for hypothesis_id, row in hypotheses.items():
        parents = tuple(row["parent_hypothesis_ids"])
        if hypothesis_id in parents:
            raise DynamicResearchError(
                "HYPOTHESIS_PARENT_SELF_REFERENCE_FORBIDDEN"
            )
        if any(parent not in hypotheses for parent in parents):
            raise DynamicResearchError("HYPOTHESIS_PARENT_UNKNOWN")
        graph[hypothesis_id] = parents

    child_ids: dict[str, list[str]] = {
        hypothesis_id: [] for hypothesis_id in graph
    }
    remaining_parent_counts = {
        hypothesis_id: len(parents)
        for hypothesis_id, parents in graph.items()
    }
    for child_id, parent_ids in graph.items():
        for parent_id in parent_ids:
            child_ids[parent_id].append(child_id)
    ready = [
        hypothesis_id
        for hypothesis_id, count in remaining_parent_counts.items()
        if count == 0
    ]
    visited_count = 0
    while ready:
        hypothesis_id = ready.pop()
        visited_count += 1
        for child_id in child_ids[hypothesis_id]:
            remaining_parent_counts[child_id] -= 1
            if remaining_parent_counts[child_id] == 0:
                ready.append(child_id)
    if visited_count != len(graph):
        raise DynamicResearchError("HYPOTHESIS_PARENT_CYCLE")


def reduce_hypothesis_registry(
    *,
    previous_registry: Mapping[str, Any] | None,
    deltas: Sequence[Mapping[str, Any]],
    decision_at: str,
    max_active_hypotheses: int = 5,
) -> dict[str, Any]:
    """Apply explicit hypothesis lifecycle deltas while preserving all history."""

    cutoff = _timestamp(decision_at, "HYPOTHESIS_REGISTRY_TIME_INVALID")
    if isinstance(max_active_hypotheses, bool) or not 1 <= max_active_hypotheses <= 20:
        raise DynamicResearchError("HYPOTHESIS_ACTIVE_BUDGET_INVALID")
    hypotheses: dict[str, dict[str, Any]] = {}
    known_ids: set[str] = set()
    known_delta_ids: set[str] = set()
    revision_history: list[dict[str, Any]] = []
    previous_digest: str | None = None
    revision = 1
    if previous_registry is not None:
        previous_digest = _verify_digest(
            previous_registry,
            "hypothesis_registry_digest",
            "HYPOTHESIS_PRIOR_DIGEST_INVALID",
        )
        revision = int(previous_registry.get("revision", 0)) + 1
        for raw in previous_registry.get("hypotheses", []):
            row = _normalize_hypothesis(raw, cutoff=cutoff)
            if row["hypothesis_id"] in hypotheses:
                raise DynamicResearchError("HYPOTHESIS_PRIOR_DUPLICATE_ID")
            hypotheses[row["hypothesis_id"]] = row
        known_ids = set(previous_registry.get("known_hypothesis_ids", hypotheses))
        known_delta_ids = set(previous_registry.get("known_delta_ids", ()))
        prior_history = previous_registry.get("revision_history", [])
        if not isinstance(prior_history, list) or any(
            not isinstance(row, Mapping) for row in prior_history
        ):
            raise DynamicResearchError("HYPOTHESIS_PRIOR_HISTORY_INVALID")
        revision_history = [dict(row) for row in prior_history]
        if not set(hypotheses).issubset(known_ids):
            raise DynamicResearchError("HYPOTHESIS_PRIOR_HISTORY_INVALID")
    _assert_hypothesis_parent_graph_acyclic(hypotheses)
    receipts: list[dict[str, Any]] = []
    for raw_delta in deltas:
        if not isinstance(raw_delta, Mapping) or set(raw_delta) != _HYPOTHESIS_DELTA_FIELDS:
            raise DynamicResearchError("HYPOTHESIS_DELTA_SCHEMA_INVALID")
        delta_id = _text(raw_delta.get("delta_id"), "HYPOTHESIS_DELTA_ID_INVALID")
        operation = str(raw_delta.get("operation") or "")
        occurred = _timestamp(raw_delta.get("occurred_at"), "HYPOTHESIS_DELTA_TIME_INVALID")
        targets = _strings(raw_delta.get("target_hypothesis_ids"), "HYPOTHESIS_DELTA_TARGET_INVALID", allow_empty=True)
        evidence_ids = _strings(raw_delta.get("evidence_ids"), "HYPOTHESIS_DELTA_EVIDENCE_INVALID", allow_empty=operation in {"ARCHIVE", "EXPIRE"})
        evidence_bindings = _normalize_evidence_bindings(
            raw_delta.get("evidence_bindings"),
            refs=evidence_ids,
            code="HYPOTHESIS_DELTA_EVIDENCE_BINDING_INVALID",
        )
        rationale = _text(raw_delta.get("agent_rationale"), "HYPOTHESIS_DELTA_RATIONALE_INVALID")
        replacements_raw = raw_delta.get("replacement_hypotheses")
        if not isinstance(replacements_raw, (list, tuple)):
            raise DynamicResearchError("HYPOTHESIS_DELTA_REPLACEMENTS_INVALID")
        replacements = [_normalize_hypothesis(row, cutoff=cutoff) for row in replacements_raw]
        matched_falsifier = raw_delta.get("matched_hard_falsifier")
        if delta_id in known_delta_ids or operation not in HYPOTHESIS_OPERATIONS or occurred > cutoff:
            raise DynamicResearchError("HYPOTHESIS_DELTA_INVALID")
        if any(target not in hypotheses for target in targets):
            raise DynamicResearchError("HYPOTHESIS_DELTA_TARGET_INVALID")
        before = {target: hypotheses[target]["state"] for target in targets}
        if operation == "CREATE":
            if targets or len(replacements) != 1 or matched_falsifier is not None:
                raise DynamicResearchError("HYPOTHESIS_CREATE_INVALID")
            new = replacements[0]
            if new["revision"] != 1 or new["hypothesis_id"] in known_ids:
                raise DynamicResearchError("HYPOTHESIS_CREATE_INVALID")
        elif operation in {"REVISE", "PROMOTE", "DEMOTE", "RESTORE"}:
            if len(targets) != 1 or len(replacements) != 1 or matched_falsifier is not None:
                raise DynamicResearchError("HYPOTHESIS_REPLACEMENT_INVALID")
            old = hypotheses[targets[0]]
            new = replacements[0]
            if new["hypothesis_id"] != targets[0] or new["revision"] != old["revision"] + 1 or new["created_at"] != old["created_at"]:
                raise DynamicResearchError("HYPOTHESIS_REVISION_CONTINUITY_INVALID")
            if new["hypothesis_type"] != old["hypothesis_type"]:
                raise DynamicResearchError("HYPOTHESIS_IDENTITY_MUTATION_FORBIDDEN")
            if operation == "RESTORE" and (old["state"] not in TERMINAL_HYPOTHESIS_STATES or new["state"] in TERMINAL_HYPOTHESIS_STATES):
                raise DynamicResearchError("HYPOTHESIS_RESTORE_INVALID")
            if operation != "RESTORE" and old["state"] in TERMINAL_HYPOTHESIS_STATES:
                raise DynamicResearchError("HYPOTHESIS_TERMINAL_MUTATION_FORBIDDEN")
            state_rank = {"DORMANT": 0, "WATCH": 1, "CANDIDATE": 2, "ACTIVE": 3}
            if operation == "REVISE" and new["state"] != old["state"]:
                raise DynamicResearchError("HYPOTHESIS_REVISE_STATE_CHANGE_FORBIDDEN")
            if operation == "PROMOTE" and (
                old["state"] not in state_rank
                or new["state"] not in state_rank
                or state_rank[new["state"]] <= state_rank[old["state"]]
            ):
                raise DynamicResearchError("HYPOTHESIS_PROMOTION_INVALID")
            if operation == "DEMOTE" and (
                old["state"] not in state_rank
                or new["state"] not in state_rank
                or state_rank[new["state"]] >= state_rank[old["state"]]
            ):
                raise DynamicResearchError("HYPOTHESIS_DEMOTION_INVALID")
        elif operation in {"SPLIT", "MERGE", "SUPERSEDE"}:
            minimum_targets = 2 if operation == "MERGE" else 1
            minimum_replacements = 2 if operation == "SPLIT" else 1
            if len(targets) < minimum_targets or len(replacements) < minimum_replacements or matched_falsifier is not None:
                raise DynamicResearchError("HYPOTHESIS_TOPOLOGY_DELTA_INVALID")
            if any(hypotheses[target]["state"] in TERMINAL_HYPOTHESIS_STATES for target in targets):
                raise DynamicResearchError("HYPOTHESIS_TERMINAL_MUTATION_FORBIDDEN")
            for new in replacements:
                if (
                    new["revision"] != 1
                    or new["hypothesis_id"] in known_ids
                    or not set(targets).issubset(new["parent_hypothesis_ids"])
                    or not set(targets).issubset(new["supersedes_ids"])
                ):
                    raise DynamicResearchError("HYPOTHESIS_TOPOLOGY_LINEAGE_INVALID")
            new = replacements[0]
        elif operation in {"INVALIDATE", "EXPIRE", "ARCHIVE"}:
            if len(targets) != 1 or replacements:
                raise DynamicResearchError("HYPOTHESIS_TERMINAL_DELTA_INVALID")
            target = hypotheses[targets[0]]
            if target["state"] in TERMINAL_HYPOTHESIS_STATES:
                raise DynamicResearchError("HYPOTHESIS_TERMINAL_MUTATION_FORBIDDEN")
            if operation == "INVALIDATE":
                if matched_falsifier not in target["hard_falsifiers"] or not evidence_ids:
                    raise DynamicResearchError("HYPOTHESIS_INVALIDATION_PROOF_MISSING")
            elif matched_falsifier is not None:
                raise DynamicResearchError("HYPOTHESIS_FALSE_FALSIFIER_BINDING")
            if operation == "EXPIRE" and occurred < _timestamp(target["expiry"], "HYPOTHESIS_EXPIRY_INVALID"):
                raise DynamicResearchError("HYPOTHESIS_EXPIRY_NOT_DUE")
            new = None
        else:
            raise DynamicResearchError("HYPOTHESIS_DELTA_INVALID")

        for target in targets:
            revision_history.append(
                {
                    "retired_by_delta_id": delta_id,
                    "retired_by_operation": operation,
                    "retired_at": raw_delta["occurred_at"],
                    "hypothesis": dict(hypotheses[target]),
                }
            )

        if operation in {"SPLIT", "MERGE", "SUPERSEDE"}:
            for target in targets:
                hypotheses[target] = {**hypotheses[target], "state": "SUPERSEDED", "updated_at": raw_delta["occurred_at"]}
        elif operation == "INVALIDATE":
            hypotheses[targets[0]] = {
                **hypotheses[targets[0]],
                "state": "INVALIDATED",
                "updated_at": raw_delta["occurred_at"],
                "active_evidence_ids": sorted(
                    set(hypotheses[targets[0]]["active_evidence_ids"])
                    | set(evidence_ids)
                ),
                "active_evidence_bindings": dict(
                    sorted(
                        {
                            **hypotheses[targets[0]][
                                "active_evidence_bindings"
                            ],
                            **evidence_bindings,
                        }.items()
                    )
                ),
            }
        elif operation == "EXPIRE":
            hypotheses[targets[0]] = {**hypotheses[targets[0]], "state": "EXPIRED", "updated_at": raw_delta["occurred_at"]}
        elif operation == "ARCHIVE":
            hypotheses[targets[0]] = {**hypotheses[targets[0]], "state": "ARCHIVED", "updated_at": raw_delta["occurred_at"]}
        if operation in {"CREATE", "REVISE", "PROMOTE", "DEMOTE", "RESTORE", "SPLIT", "MERGE", "SUPERSEDE"}:
            available_parent_ids = set(hypotheses)
            for replacement in replacements:
                hypothesis_id = replacement["hypothesis_id"]
                if hypothesis_id in known_ids and hypothesis_id not in targets:
                    raise DynamicResearchError("HYPOTHESIS_ID_REUSE_INVALID")
                if hypothesis_id in replacement["parent_hypothesis_ids"]:
                    raise DynamicResearchError(
                        "HYPOTHESIS_PARENT_SELF_REFERENCE_FORBIDDEN"
                    )
                if any(
                    parent not in available_parent_ids
                    for parent in replacement["parent_hypothesis_ids"]
                ):
                    raise DynamicResearchError("HYPOTHESIS_PARENT_UNKNOWN")
                hypotheses[hypothesis_id] = replacement
                known_ids.add(hypothesis_id)
        _assert_hypothesis_parent_graph_acyclic(hypotheses)
        dedup_keys = [row["deduplication_key"] for row in hypotheses.values() if row["state"] not in TERMINAL_HYPOTHESIS_STATES]
        if len(dedup_keys) != len(set(dedup_keys)):
            raise DynamicResearchError("DUPLICATE_HYPOTHESIS")
        semantic_fingerprints = [
            _hypothesis_semantic_fingerprint(row)
            for row in hypotheses.values()
            if row["state"] not in TERMINAL_HYPOTHESIS_STATES
        ]
        if len(semantic_fingerprints) != len(set(semantic_fingerprints)):
            raise DynamicResearchError("DUPLICATE_HYPOTHESIS_SEMANTICS")
        receipts.append(
            self_digest(
                {
                    "schema_id": "hypothesis_registry_transition_receipt",
                    "schema_version": "1.0.0",
                    "delta_id": delta_id,
                    "operation": operation,
                    "occurred_at": raw_delta["occurred_at"],
                    "targets": list(targets),
                    "replacement_ids": [row["hypothesis_id"] for row in replacements],
                    "evidence_ids": list(evidence_ids),
                    "evidence_bindings": evidence_bindings,
                    "matched_hard_falsifier": matched_falsifier,
                    "before_states": before,
                    "after_states": {item: hypotheses[item]["state"] for item in set(targets) | {row["hypothesis_id"] for row in replacements}},
                    "agent_rationale": rationale,
                },
                "transition_digest",
            )
        )
        known_delta_ids.add(delta_id)
    active_ids = sorted(
        row["hypothesis_id"] for row in hypotheses.values() if row["state"] == "ACTIVE"
    )
    if len(active_ids) > max_active_hypotheses:
        raise DynamicResearchError("HYPOTHESIS_ACTIVE_BUDGET_EXCEEDED")
    registry = {
        "schema_id": "dynamic_hypothesis_registry",
        "schema_version": "1.0.0",
        "revision": revision,
        "decision_at": decision_at,
        "previous_hypothesis_registry_digest": previous_digest,
        "max_active_hypotheses": max_active_hypotheses,
        "active_hypothesis_ids": active_ids,
        "hypotheses": sorted(hypotheses.values(), key=lambda row: row["hypothesis_id"]),
        "revision_history": revision_history,
        "known_hypothesis_ids": sorted(known_ids),
        "known_delta_ids": sorted(known_delta_ids),
        "applied_delta_ids": [row["delta_id"] for row in receipts],
        "transition_receipts": receipts,
        "semantic_family_whitelist": None,
        "semantic_deduplication": "DETERMINISTIC_CONTRACT_FINGERPRINT_PLUS_AGENT_KEY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(registry, "hypothesis_registry_digest")


def _normalize_expectation(raw: Mapping[str, Any], *, cutoff: datetime) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _EXPECTATION_FIELDS:
        raise DynamicResearchError("EXPECTATION_SCHEMA_INVALID")
    expectation_id = _text(raw.get("expectation_id"), "EXPECTATION_ID_INVALID")
    revision = raw.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise DynamicResearchError("EXPECTATION_REVISION_INVALID")
    created = _timestamp(raw.get("created_at"), "EXPECTATION_TIME_INVALID")
    updated = _timestamp(raw.get("updated_at"), "EXPECTATION_TIME_INVALID")
    start = _timestamp(raw.get("observation_start"), "EXPECTATION_TIME_INVALID")
    deadline = _timestamp(raw.get("observation_deadline"), "EXPECTATION_TIME_INVALID")
    if created > updated or updated > cutoff or deadline <= start:
        raise DynamicResearchError("EXPECTATION_TIME_INVALID")
    status = str(raw.get("status") or "")
    if status not in EXPECTATION_STATUSES or raw.get("evidence_sufficiency") not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
        raise DynamicResearchError("EXPECTATION_ENUM_INVALID")
    closed_at = raw.get("closed_at")
    if status in TERMINAL_EXPECTATION_STATUSES:
        closed = _timestamp(closed_at, "EXPECTATION_CLOSE_TIME_INVALID")
        if closed < created or closed > cutoff or not raw.get("result_evidence_refs") or not str(raw.get("result_note") or "").strip():
            raise DynamicResearchError("EXPECTATION_TERMINAL_RESULT_INCOMPLETE")
    elif closed_at is not None:
        raise DynamicResearchError("EXPECTATION_NONTERMINAL_CLOSE_FORBIDDEN")
    observations: dict[str, list[dict[str, str]]] = {}
    for field in ("expected_observations", "falsifying_observations"):
        values = raw.get(field)
        if not isinstance(values, (list, tuple)) or not values:
            raise DynamicResearchError("EXPECTATION_OBSERVATIONS_INVALID")
        normalized_values: list[dict[str, str]] = []
        for value in values:
            if not isinstance(value, Mapping) or set(value) != _EXPECTATION_OBSERVATION_FIELDS:
                raise DynamicResearchError("EXPECTATION_OBSERVATION_SCHEMA_INVALID")
            normalized_values.append(
                {key: _text(value.get(key), "EXPECTATION_OBSERVATION_INVALID") for key in _EXPECTATION_OBSERVATION_FIELDS}
            )
        observations[field] = normalized_values
    normalized = {
        **dict(raw),
        "expectation_id": expectation_id,
        "hypothesis_id": _text(raw.get("hypothesis_id"), "EXPECTATION_HYPOTHESIS_INVALID"),
        "deduplication_key": _text(raw.get("deduplication_key"), "EXPECTATION_DEDUP_KEY_INVALID"),
        "if_conditions": list(_strings(raw.get("if_conditions"), "EXPECTATION_CONDITIONS_INVALID")),
        "expected_observations": observations["expected_observations"],
        "falsifying_observations": observations["falsifying_observations"],
        "result_evidence_refs": list(_strings(raw.get("result_evidence_refs"), "EXPECTATION_RESULT_EVIDENCE_INVALID", allow_empty=status not in TERMINAL_EXPECTATION_STATUSES)),
    }
    normalized["result_evidence_bindings"] = _normalize_evidence_bindings(
        raw.get("result_evidence_bindings"),
        refs=normalized["result_evidence_refs"],
        code="EXPECTATION_RESULT_EVIDENCE_BINDING_INVALID",
    )
    if status == "OPEN" and (
        normalized["result_evidence_refs"] or raw.get("result_note") is not None
    ):
        raise DynamicResearchError("EXPECTATION_OPEN_RESULT_FORBIDDEN")
    if status == "PARTIAL" and (
        not normalized["result_evidence_refs"]
        or not isinstance(raw.get("result_note"), str)
        or not str(raw.get("result_note")).strip()
    ):
        raise DynamicResearchError("EXPECTATION_PARTIAL_RESULT_INCOMPLETE")
    parent = raw.get("parent_expectation_id")
    if parent is not None and (not isinstance(parent, str) or not parent):
        raise DynamicResearchError("EXPECTATION_PARENT_INVALID")
    if parent == expectation_id:
        raise DynamicResearchError(
            "EXPECTATION_PARENT_SELF_REFERENCE_FORBIDDEN"
        )
    return normalized


def _expectation_semantic_fingerprint(row: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "hypothesis_id": row["hypothesis_id"],
            "parent_expectation_id": row["parent_expectation_id"],
            "observation_start": row["observation_start"],
            "observation_deadline": row["observation_deadline"],
            "if_conditions": row["if_conditions"],
            "expected_observations": row["expected_observations"],
            "falsifying_observations": row["falsifying_observations"],
        }
    )


def _assert_expectation_parent_graph_acyclic(
    expectations: Mapping[str, Mapping[str, Any]],
) -> None:
    """Require expectation lineage to be an existing-node DAG."""

    graph: dict[str, str | None] = {}
    for expectation_id, row in expectations.items():
        parent = row["parent_expectation_id"]
        if parent == expectation_id:
            raise DynamicResearchError(
                "EXPECTATION_PARENT_SELF_REFERENCE_FORBIDDEN"
            )
        if parent is not None and parent not in expectations:
            raise DynamicResearchError("EXPECTATION_PARENT_UNKNOWN")
        graph[expectation_id] = parent

    child_ids: dict[str, list[str]] = {
        expectation_id: [] for expectation_id in graph
    }
    remaining_parent_counts = {
        expectation_id: int(parent is not None)
        for expectation_id, parent in graph.items()
    }
    for child_id, parent_id in graph.items():
        if parent_id is not None:
            child_ids[parent_id].append(child_id)
    ready = [
        expectation_id
        for expectation_id, count in remaining_parent_counts.items()
        if count == 0
    ]
    visited_count = 0
    while ready:
        expectation_id = ready.pop()
        visited_count += 1
        for child_id in child_ids[expectation_id]:
            remaining_parent_counts[child_id] -= 1
            if remaining_parent_counts[child_id] == 0:
                ready.append(child_id)
    if visited_count != len(graph):
        raise DynamicResearchError("EXPECTATION_PARENT_CYCLE")


def reduce_expectation_ledger(
    *,
    previous_ledger: Mapping[str, Any] | None,
    deltas: Sequence[Mapping[str, Any]],
    decision_at: str,
    valid_hypothesis_ids: Sequence[str],
) -> dict[str, Any]:
    """Apply append-only expectation revisions and explicit result closure."""

    cutoff = _timestamp(decision_at, "EXPECTATION_LEDGER_TIME_INVALID")
    valid_hypotheses = set(_strings(valid_hypothesis_ids, "EXPECTATION_HYPOTHESIS_SET_INVALID"))
    expectations: dict[str, dict[str, Any]] = {}
    known_ids: set[str] = set()
    known_delta_ids: set[str] = set()
    known_dedup_keys: set[str] = set()
    revision_history: list[dict[str, Any]] = []
    previous_digest: str | None = None
    revision = 1
    if previous_ledger is not None:
        previous_digest = _verify_digest(previous_ledger, "expectation_ledger_digest", "EXPECTATION_PRIOR_DIGEST_INVALID")
        revision = int(previous_ledger.get("revision", 0)) + 1
        for raw in previous_ledger.get("expectations", []):
            row = _normalize_expectation(raw, cutoff=cutoff)
            if row["expectation_id"] in expectations:
                raise DynamicResearchError("EXPECTATION_PRIOR_DUPLICATE_ID")
            expectations[row["expectation_id"]] = row
        known_ids = set(previous_ledger.get("known_expectation_ids", expectations))
        known_delta_ids = set(previous_ledger.get("known_delta_ids", ()))
        known_dedup_keys = set(previous_ledger.get("known_deduplication_keys", (row["deduplication_key"] for row in expectations.values())))
        prior_history = previous_ledger.get("revision_history", [])
        if not isinstance(prior_history, list) or any(
            not isinstance(row, Mapping) for row in prior_history
        ):
            raise DynamicResearchError("EXPECTATION_PRIOR_HISTORY_INVALID")
        revision_history = [dict(row) for row in prior_history]
    _assert_expectation_parent_graph_acyclic(expectations)
    receipts: list[dict[str, Any]] = []
    for raw_delta in deltas:
        if not isinstance(raw_delta, Mapping) or set(raw_delta) != _EXPECTATION_DELTA_FIELDS:
            raise DynamicResearchError("EXPECTATION_DELTA_SCHEMA_INVALID")
        delta_id = _text(raw_delta.get("delta_id"), "EXPECTATION_DELTA_ID_INVALID")
        operation = str(raw_delta.get("operation") or "")
        occurred = _timestamp(raw_delta.get("occurred_at"), "EXPECTATION_DELTA_TIME_INVALID")
        target = raw_delta.get("target_expectation_id")
        rationale = _text(raw_delta.get("agent_rationale"), "EXPECTATION_DELTA_RATIONALE_INVALID")
        expectation = _normalize_expectation(raw_delta.get("expectation"), cutoff=cutoff)
        if delta_id in known_delta_ids or operation not in EXPECTATION_OPERATIONS or occurred > cutoff:
            raise DynamicResearchError("EXPECTATION_DELTA_INVALID")
        if expectation["hypothesis_id"] not in valid_hypotheses:
            raise DynamicResearchError("EXPECTATION_HYPOTHESIS_INVALID")
        before_status: str | None = None
        if operation == "CREATE":
            if target is not None or expectation["expectation_id"] in known_ids or expectation["revision"] != 1 or expectation["status"] != "OPEN":
                raise DynamicResearchError("EXPECTATION_CREATE_INVALID")
            if expectation["deduplication_key"] in known_dedup_keys:
                raise DynamicResearchError("DUPLICATE_EXPECTATION")
            if any(
                _expectation_semantic_fingerprint(row)
                == _expectation_semantic_fingerprint(expectation)
                for row in expectations.values()
            ):
                raise DynamicResearchError("DUPLICATE_EXPECTATION_SEMANTICS")
        else:
            if not isinstance(target, str) or target not in expectations or expectation["expectation_id"] != target:
                raise DynamicResearchError("EXPECTATION_DELTA_TARGET_INVALID")
            old = expectations[target]
            before_status = old["status"]
            if old["status"] in TERMINAL_EXPECTATION_STATUSES or expectation["revision"] != old["revision"] + 1 or expectation["created_at"] != old["created_at"] or expectation["deduplication_key"] != old["deduplication_key"]:
                raise DynamicResearchError("EXPECTATION_REVISION_CONTINUITY_INVALID")
            if operation == "REVISE" and expectation["status"] not in {"OPEN", "PARTIAL"}:
                raise DynamicResearchError("EXPECTATION_REVISE_STATUS_INVALID")
            if operation == "UPDATE_RESULT" and expectation["status"] != "PARTIAL":
                raise DynamicResearchError("EXPECTATION_UPDATE_STATUS_INVALID")
            if operation == "CLOSE" and expectation["status"] not in TERMINAL_EXPECTATION_STATUSES:
                raise DynamicResearchError("EXPECTATION_CLOSE_STATUS_INVALID")
            if (
                expectation["status"] == "EXPIRED"
                and occurred
                < _timestamp(
                    expectation["observation_deadline"],
                    "EXPECTATION_TIME_INVALID",
                )
            ):
                raise DynamicResearchError("EXPECTATION_EXPIRY_NOT_DUE")
            revision_history.append(
                {
                    "retired_by_delta_id": delta_id,
                    "retired_by_operation": operation,
                    "retired_at": raw_delta["occurred_at"],
                    "expectation": dict(old),
                }
            )
        parent = expectation["parent_expectation_id"]
        if parent is not None and parent not in expectations:
            raise DynamicResearchError("EXPECTATION_PARENT_UNKNOWN")
        expectations[expectation["expectation_id"]] = expectation
        _assert_expectation_parent_graph_acyclic(expectations)
        known_ids.add(expectation["expectation_id"])
        known_dedup_keys.add(expectation["deduplication_key"])
        known_delta_ids.add(delta_id)
        receipts.append(
            self_digest(
                {
                    "schema_id": "expectation_ledger_transition_receipt",
                    "schema_version": "1.0.0",
                    "delta_id": delta_id,
                    "operation": operation,
                    "occurred_at": raw_delta["occurred_at"],
                    "expectation_id": expectation["expectation_id"],
                    "before_status": before_status,
                    "after_status": expectation["status"],
                    "expectation_revision": expectation["revision"],
                    "result_evidence_refs": expectation["result_evidence_refs"],
                    "result_evidence_bindings": expectation[
                        "result_evidence_bindings"
                    ],
                    "agent_rationale": rationale,
                },
                "transition_digest",
            )
        )
    ledger = {
        "schema_id": "append_only_expectation_ledger",
        "schema_version": "1.0.0",
        "revision": revision,
        "decision_at": decision_at,
        "previous_expectation_ledger_digest": previous_digest,
        "expectations": sorted(expectations.values(), key=lambda row: row["expectation_id"]),
        "revision_history": revision_history,
        "open_expectation_ids": sorted(row["expectation_id"] for row in expectations.values() if row["status"] in {"OPEN", "PARTIAL"}),
        "known_expectation_ids": sorted(known_ids),
        "known_deduplication_keys": sorted(known_dedup_keys),
        "known_delta_ids": sorted(known_delta_ids),
        "applied_delta_ids": [row["delta_id"] for row in receipts],
        "transition_receipts": receipts,
        "probability_status": "EVIDENCE_SUFFICIENCY_ORDINAL_NOT_PROBABILITY",
        "semantic_deduplication": "DETERMINISTIC_CONTRACT_FINGERPRINT_PLUS_AGENT_KEY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
    }
    return self_digest(ledger, "expectation_ledger_digest")
