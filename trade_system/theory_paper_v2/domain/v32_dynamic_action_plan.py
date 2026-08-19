"""Pure V3.2 dynamic action-planning and reference-risk contracts.

The objects in this module are research plans, not orders or portfolio truth.
They bind a verified V3.2 dynamic-research state, enumerate every legal
adjacent action for a *research intent*, allocate a dimensionless reference
risk budget after dependency-cluster de-duplication, and fail closed on the
specific shortcuts V3.2 forbids: generic-uncertainty WAIT, averaging down,
atomic reversal, nominal-position allocation, and "market money" reasoning.

This module owns no filesystem, clock, network, account, fill, PnL, execution,
Agent transport, or authority-loading behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Mapping, Sequence

from .contracts.canonical import canonical_decimal, self_digest, verify_self_digest
from .v32_dynamic_research import (
    ACTIONABLE_HYPOTHESIS_STATUSES,
    NON_DIRECTIONAL_MARKET_REGIMES,
    SUBJECTIVE_PLAUSIBILITY_TIERS,
    SUBJECTIVE_TIER_ORDER,
    SUBJECTIVE_TIER_RISK_CAP_UNITS,
    verify_v32_dynamic_research_state_v1,
)


class V32DynamicActionPlanError(ValueError):
    """A V3.2 planning or reference-risk invariant failed closed."""


SCHEMA_ID = "theory_paper_v32_dynamic_action_plan_v1"
SCHEMA_VERSION = "1.1.0"
DIGEST_FIELD = "dynamic_action_plan_digest"

ACTION_KINDS = (
    "OPEN_PROBE",
    "ADD",
    "HOLD",
    "REDUCE",
    "CLOSE",
    "REENTER",
    "REVERSE",
    "WAIT",
)
ACTION_DIRECTIONS = ("LONG", "SHORT", "NONE")
REFERENCE_CONTEXTS = (
    "FLAT_RESEARCH_INTENT",
    "LONG_RESEARCH_INTENT",
    "SHORT_RESEARCH_INTENT",
    "REENTRY_LONG_RESEARCH_INTENT",
    "REENTRY_SHORT_RESEARCH_INTENT",
)
PLAN_STATES = ("PLANNED", "CONDITIONAL", "CANCELLED", "EXPIRED", "SUPERSEDED")
ENTRY_MODES = (
    "ANTICIPATORY_PROBE",
    "REACTION_ENTRY",
    "BREAK_ACCELERATION",
    "RETEST_OR_REENTRY",
)
FEASIBILITY_STATES = ("ELIGIBLE", "BLOCKED")
BLOCK_REASONS = (
    "NONE",
    "FACT_INTEGRITY",
    "MAX_LOSS",
    "COST_OR_LIQUIDITY",
    "GEOMETRY",
    "MISSING_PARENT_PLAN",
    "NO_NEW_EVIDENCE",
    "REENTRY_CONDITION_NOT_MET",
    "REENTRY_COOLDOWN_OR_BUDGET",
    "MARKET_REGIME_NON_DIRECTIONAL",
    "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
    "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
    "PATH_MODIFIER_INVALIDATION",
)
WAIT_DOMINANCE_REASONS = (
    "COST_OR_LIQUIDITY_DOMINATES",
    "GEOMETRY_DOMINATES",
    "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE",
    "CORRELATED_RISK_BUDGET_DOMINATES",
)
TAKE_PROFIT_ACTIONS = (
    "PARTIAL_HARVEST",
    "TIGHTEN_PROTECTION",
    "RUNNER_REASSESS",
)
TRAILING_MODES = (
    "STRUCTURE_VOLATILITY_LOCKED_NET",
    "STRUCTURE_TIME_EVENT_LOCKED_NET",
)

RISK_INCREASING_ACTIONS = frozenset(
    {"OPEN_PROBE", "ADD", "REENTER", "REVERSE"}
)
INSTRUMENT_CHURN_ACTION_KINDS = frozenset(
    {"OPEN_PROBE", "REENTER", "REVERSE"}
)
REFERENCE_RISK_QUANTUM = Decimal("0.000001")
OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE_REF = (
    "objective-reference-risk-inputs-unavailable"
)
NO_NEW_CURRENT_PIT_EVIDENCE_REF = (
    "no-new-current-pit-evidence-since-predecessor"
)
CURRENT_PILOT_REFERENCE_RISK_ENVELOPE = Decimal("1")
CURRENT_PILOT_REENTRY_WINDOW_SECONDS = 86400
CURRENT_PILOT_REENTRY_CHURN_SCOPE = "RUN_SINGLE_INSTRUMENT_WIDE"
CURRENT_PILOT_REENTRY_WINDOW_POLICY = "ABSOLUTE_24H_NO_EARLY_RESET"
CURRENT_PILOT_WATCHDOG_MAX_WAIT_CYCLES = 8
CURRENT_PILOT_WATCHDOG_MAX_INACTIVITY_SECONDS = 7200
WATCHDOG_REQUIRED_RESPONSES = (
    "BASELINE_COMPARISON",
    "FULL_OPPORTUNITY_REVIEW",
    "SHADOW_PLAN_REFRESH",
)
REQUIRED_EXECUTION_HAZARD_SCENARIOS = (
    "CANCEL_REPLACE_RACE",
    "LIMIT_NOT_FILLED_OR_QUEUE_LOSS",
    "NETWORK_TIMEOUT_OR_PARTITION",
    "PROTECTION_ACK_UNKNOWN",
    "RATE_LIMIT_OR_REJECTION",
    "STOP_THROUGH_OR_GAP",
    "VENUE_UNAVAILABLE",
)
FUTURE_EXECUTION_CONTROL_REQUIREMENTS = (
    "ACK_STATE_MACHINE",
    "ATOMIC_ATTACHED_PROTECTION_CAPABILITY_MUST_BE_VENUE_QUALIFIED",
    "CIRCUIT_BREAKER",
    "DISCONNECT_RECOVERY",
    "FINAL_POSITION_TRUTH_RECONCILIATION",
    "FREEZE_NEW_RISK_ON_EXECUTION_ANOMALY",
    "IDEMPOTENT_CLIENT_ID",
    "IDEMPOTENT_REDUCE_ONLY_IOC_OR_MARKETABLE_THEN_MARKET_FALLBACK_WHEN_SEPARATELY_AUTHORIZED",
    "NO_FILL_PRICE_OR_FLAT_POSITION_GUARANTEE",
    "NO_NEW_ENTRY_IF_ATOMIC_ATTACHED_PROTECTION_IS_UNSUPPORTED_OR_UNQUALIFIED",
    "POST_FILL_PRE_PROTECTION_ACK_IS_UNPROTECTED_EXPOSURE_FREEZE_NEW_RISK_AND_ONLY_PREAUTHORIZED_REDUCE_ONLY_CLOSE_OR_RECONCILE",
    "UNRESOLVED_EXPOSURE_ALERT_AND_HUMAN_ESCALATION_IF_VENUE_UNAVAILABLE",
)
PATH_MODIFIER_RISK_CAPS = {
    "SUPPORTS_PATH": 100,
    "MODULATES_PATH": 50,
    "OPPOSES_PATH": 50,
    "INVALIDATES_PATH": 0,
}
UNKNOWN_PATH_MODIFIER_RISK_CAP = 50
MAX_ACTION_CANDIDATES = 16
REENTRY_MAX_ATTEMPTS = 2
REENTRY_MAX_CONSECUTIVE_FAILURES = 2
REENTRY_MAX_CUMULATIVE_REFERENCE_RISK = (
    CURRENT_PILOT_REFERENCE_RISK_ENVELOPE * REENTRY_MAX_ATTEMPTS
)
INSTRUMENT_CHURN_BUDGET_LIMIT_REACHED_REF = (
    "system:instrument-churn-budget-limit-reached"
)
CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES = (
    NON_DIRECTIONAL_MARKET_REGIMES | frozenset({"TRANSITION"})
)
TIER_ALLOCATION_UNITS = {
    "EXTREME_UNCERTAINTY": 0,
    "LOW": 1,
    "HIGH": 2,
}

_LEGAL_ACTION_GRID: dict[str, tuple[tuple[str, str], ...]] = {
    "FLAT_RESEARCH_INTENT": (
        ("OPEN_PROBE", "LONG"),
        ("OPEN_PROBE", "SHORT"),
        ("WAIT", "NONE"),
    ),
    "LONG_RESEARCH_INTENT": (
        ("ADD", "LONG"),
        ("HOLD", "LONG"),
        ("REDUCE", "LONG"),
        ("CLOSE", "LONG"),
        ("REVERSE", "SHORT"),
    ),
    "SHORT_RESEARCH_INTENT": (
        ("ADD", "SHORT"),
        ("HOLD", "SHORT"),
        ("REDUCE", "SHORT"),
        ("CLOSE", "SHORT"),
        ("REVERSE", "LONG"),
    ),
    "REENTRY_LONG_RESEARCH_INTENT": (
        ("REENTER", "LONG"),
        ("OPEN_PROBE", "SHORT"),
        ("WAIT", "NONE"),
    ),
    "REENTRY_SHORT_RESEARCH_INTENT": (
        ("REENTER", "SHORT"),
        ("OPEN_PROBE", "LONG"),
        ("WAIT", "NONE"),
    ),
}

_CANDIDATE_FIELDS = frozenset(
    {
        "candidate_id",
        "action_kind",
        "direction",
        "plan_state",
        "feasibility",
        "block_reason",
        "blocking_unknown_ids",
        "blocking_evidence_refs",
        "trigger_conditions",
        "guard_conditions",
        "invalidation_conditions",
        "horizon_at",
        "next_observation",
        "opportunity_cost",
        "hypothesis_ids",
        "cluster_ids",
        "zone_ids",
        "risk_tranche_id",
        "parent_tranche_id",
        "close_first_candidate_id",
        "reentry_obligation_id",
        "new_evidence_refs",
    }
)
_RESEARCH_BREAKOUT_TRIGGER_LEG_FIELDS = frozenset(
    {
        "candidate_id",
        "direction",
        "zone_id",
        "boundary_field",
        "threshold_value",
        "comparator",
    }
)
_RESEARCH_BREAKOUT_TRIGGER_PAIR_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "pair_id",
        "source_component_id",
        "source_scope",
        "timeframe",
        "observed_field",
        "closed_bar_required",
        "required_consecutive_closed_bars",
        "valid_from",
        "expires_at",
        "pit_rule",
        "resolution_policy",
        "match_effect",
        "status",
        "legs",
        "external_execution_authority",
        "order_claim",
        "oco_claim",
        "executable",
    }
)
_REFERENCE_TRANCHE_STATE_FIELDS = frozenset(
    {
        "status",
        "tranche_id",
        "direction",
        "entry_reference",
        "protective_stop_reference",
        "valid_until",
        "supporting_hypothesis_ids",
        "supporting_cluster_ids",
        "zone_ids",
    }
)
_TRANCHE_INPUT_FIELDS = frozenset(
    {
        "tranche_id",
        "candidate_id",
        "entry_mode",
        "conditional_entry_reference",
        "protective_stop_reference",
        "previous_stop_reference",
        "parent_entry_reference",
        "minimum_noise_execution_buffer",
        "multiplier_reference",
        "fee_stress_reference",
        "slippage_stress_reference",
        "funding_bound_reference",
        "tail_gap_reference",
        "reference_scale_quantum",
        "supporting_cluster_ids",
        "shared_falsifiers",
        "independent_falsifiers",
        "take_profit_targets",
        "trailing_plan",
        "time_stop_at",
        "event_risk_guards",
        "reentry_obligation_id",
        "new_evidence_refs",
    }
)
_TRANCHE_COMPUTED_FIELDS = frozenset(
    {"reference_risk_budget", "unit_loss_reference", "derived_reference_scale"}
)
_TRANCHE_DOCUMENT_FIELDS = _TRANCHE_INPUT_FIELDS | _TRANCHE_COMPUTED_FIELDS
_TAKE_PROFIT_FIELDS = frozenset(
    {
        "target_id",
        "management_action",
        "reference_price",
        "trigger_condition",
        "reference_fraction",
        "preserves_runner",
    }
)
_TRAILING_FIELDS = frozenset(
    {
        "mode",
        "activation_conditions",
        "update_rule",
        "basis_refs",
        "moves_only_to_reduce_stress",
        "locked_net_required_before_risk_release",
        "floating_gain_is_market_money",
    }
)
_REENTRY_FIELDS = frozenset(
    {
        "obligation_id",
        "source_tranche_id",
        "direction",
        "plan_state",
        "parent_hypothesis_ids",
        "supporting_cluster_ids",
        "observation_conditions",
        "hard_falsifiers",
        "max_wait_until",
        "requires_new_risk_budget",
        "rewrites_prior_exit",
    }
)
_REENTRY_BUDGET_FIELDS = frozenset(
    {
        "budget_id",
        "churn_scope",
        "instrument",
        "window_policy",
        "failure_cluster_id",
        "direction",
        "rolling_window_started_at",
        "rolling_window_expires_at",
        "attempts_used",
        "max_attempts",
        "cumulative_reference_risk",
        "max_cumulative_reference_risk",
        "consecutive_failures",
        "cooldown_until",
        "failure_evidence_refs",
        "reset_independent_cluster_id",
        "reset_previous_regime",
        "reset_current_regime",
        "reset_new_tranche_id",
        "reset_evidence_refs",
        "status",
        "obligation_forces_entry",
    }
)
REENTRY_BUDGET_STATUSES = (
    "INACTIVE",
    "INITIAL_PROBE_USED",
    "AVAILABLE",
    "COOLDOWN",
    "EXHAUSTED",
    "RESET",
)
_WAIT_COMPARISON_FIELDS = frozenset(
    {"candidate_id", "dominance_reason", "evidence_refs", "rationale"}
)
_WAIT_FIELDS = frozenset(
    {
        "delay_cost",
        "missed_move_risk",
        "information_value",
        "next_observation",
        "review_deadline",
        "dominance_comparisons",
    }
)
_RISK_AVAILABILITY_FIELDS = frozenset(
    {
        "derivation_policy",
        "hypothesis_evidence_chain_coverage",
        "hypothesis_evidence_refs",
        "missing_hypothesis_evidence_requirements",
        "source_admission_coverage_status",
        "regime_gate_status",
        "geometry_gate_status",
    }
)
_WATCHDOG_FIELDS = frozenset(
    {
        "inactivity_since",
        "consecutive_wait_cycles",
        "testable_risk_plan_review_due",
        "model_adaptation_inactivity_since",
        "consecutive_model_stale_cycles",
        "model_adaptation_review_due",
        "max_wait_cycles_before_review",
        "max_inactivity_seconds",
        "forced_review_due",
        "required_responses",
        "baseline_comparison_refs",
        "shadow_plan_candidate_ids",
        "next_watchdog_review_at",
        "forces_action",
        "shadow_plan_scope",
        "clock_semantics",
        "real_exposure_claim",
    }
)
_EXECUTION_HAZARD_FIELDS = frozenset(
    {
        "hazard_id",
        "future_latency_bound_ms",
        "latency_qualification_status",
        "latency_evidence_refs",
        "network_failure_scenario",
        "required_scenarios",
        "future_execution_control_requirements",
        "unbounded_venue_outage_status",
        "guaranteed_exit_price",
        "model_scope",
        "stop_semantics",
        "current_order_claim",
        "current_protection_claim",
    }
)
_PATH_MODIFIER_ASSESSMENT_FIELDS = frozenset(
    {
        "candidate_id",
        "applicable_modifier_ids",
        "active_modifier_ids",
        "invalidating_modifier_ids",
        "risk_cap_units",
        "risk_effect_policy",
    }
)
_EXECUTION_GATE_FIELDS = frozenset(
    {
        "current_execution_eligibility",
        "block_reasons",
        "research_candidates_remain_comparable",
        "order_submission_allowed",
        "stop_trigger_is_fill",
        "unbounded_venue_outage_resolved",
        "required_future_controls",
    }
)
_STATE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "cycle_index",
        "plan_id",
        "as_of",
        "expires_at",
        "dynamic_research_state_digest",
        "reference_context",
        "reference_tranche_state",
        "plan_state",
        "reference_risk_unit_budget",
        "subjective_tier_cap_units",
        "directional_subjective_tier_cap_units",
        "residual_uncertainty_tier",
        "residual_uncertainty_cap_units",
        "risk_bottleneck_cap_units",
        "path_modifier_candidate_assessments",
        "pre_modifier_reference_risk_budget",
        "risk_availability_assessment",
        "distributable_reference_risk_budget",
        "selected_candidate_reference_risk_budget",
        "current_executable_reference_risk_budget",
        "legal_actions_considered",
        "candidates",
        "research_breakout_trigger_pairs",
        "cluster_risk_allocations",
        "risk_tranches",
        "reentry_obligations",
        "reentry_budget_state",
        "selected_candidate_id",
        "alternative_candidate_rank",
        "wait_assessment",
        "inactivity_opportunity_watchdog",
        "future_execution_hazard",
        "execution_gate",
        "risk_allocation_policy",
        "resource_limits",
        "resource_policy",
        "planning_scope",
        "source_scope",
        "external_execution_authority",
        "execution_claim",
        "account_claim",
        "fill_claim",
        "pnl_claim",
        "market_money_claim",
        "probability_claim",
        "expected_value_allowed",
        "executable",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32DynamicActionPlanError(code)
    return value


def _instrument_churn_budget_id(*, run_id: str, instrument: str) -> str:
    """Return the sole reentry-ledger identity for one run/instrument."""

    return f"instrument-churn::{run_id}::{instrument}"


def v32_action_consumes_instrument_churn_budget_v1(
    *, action_kind: str, reentry_budget_status: str
) -> bool:
    """Classify one selected action against the sole instrument churn ledger.

    Canonical REENTER always remains a counted reentry action.  Once the same
    run/instrument ledger is active, selecting OPEN_PROBE or REVERSE is also a
    churn attempt regardless of direction.  An initial OPEN_PROBE while the
    ledger is INACTIVE does not consume a reentry attempt, but continuity must
    arm INITIAL_PROBE_USED so another unfailed "initial" probe is impossible.
    """

    action = _text(action_kind, "V32_ACTION_INSTRUMENT_CHURN_ACTION_INVALID")
    status = _text(
        reentry_budget_status, "V32_ACTION_INSTRUMENT_CHURN_STATUS_INVALID"
    )
    if action not in ACTION_KINDS:
        raise V32DynamicActionPlanError(
            "V32_ACTION_INSTRUMENT_CHURN_ACTION_INVALID"
        )
    if status not in REENTRY_BUDGET_STATUSES:
        raise V32DynamicActionPlanError(
            "V32_ACTION_INSTRUMENT_CHURN_STATUS_INVALID"
        )
    return action == "REENTER" or (
        status != "INACTIVE" and action in INSTRUMENT_CHURN_ACTION_KINDS
    )


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32DynamicActionPlanError(code) from exc
    if parsed.tzinfo is None:
        raise V32DynamicActionPlanError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32DynamicActionPlanError(code)
    return text


def _moment(value: Any, code: str) -> datetime:
    return datetime.fromisoformat(_time(value, code).replace("Z", "+00:00")).astimezone(
        UTC
    )


def _decimal(value: Any, code: str, *, nonnegative: bool = True) -> Decimal:
    if isinstance(value, (float, bool)):
        raise V32DynamicActionPlanError(code)
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise V32DynamicActionPlanError(code) from exc
    if not parsed.is_finite() or (nonnegative and parsed < 0):
        raise V32DynamicActionPlanError(code)
    return parsed


def _nullable_decimal(value: Any, code: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, code)


def _strings(values: Any, code: str, *, allow_empty: bool = False) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise V32DynamicActionPlanError(code)
    result = [_text(item, code) for item in values]
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise V32DynamicActionPlanError(code)
    return sorted(result)


def _ordered_strings(
    values: Any, code: str, *, allow_empty: bool = False
) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise V32DynamicActionPlanError(code)
    result = [_text(item, code) for item in values]
    if (not allow_empty and not result) or len(result) != len(set(result)):
        raise V32DynamicActionPlanError(code)
    return result


def _nullable_id(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _text(value, code)


def _nullable_time(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _time(value, code)


def _frozen_cap_units(value: Any, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value not in {0, 50, 100}
    ):
        raise V32DynamicActionPlanError(code)
    return value


def _current_state_pit_evidence_refs(
    state: Mapping[str, Any],
) -> frozenset[str]:
    refs: set[str] = set()
    regime = state["market_regime_state"]
    refs.update(regime["evidence_refs"])
    refs.update(regime["counter_evidence_refs"])
    refs.update(regime["transition_evidence_refs"])
    for zone in state["zones"]:
        for field in (
            "evidence_refs",
            "touch_refs",
            "reaction_refs",
            "volume_at_price_refs",
            "dwell_time_refs",
            "round_number_refs",
            "orderbook_flow_refs",
            "leverage_refs",
            "options_refs",
        ):
            refs.update(zone[field])
    for hypothesis in state["hypotheses"]:
        for field in (
            "source_refs",
            "supporting_refs",
            "opposing_refs",
            "tier_update_refs",
            "renewal_evidence_refs",
        ):
            refs.update(hypothesis[field])
    for modifier in state["path_modifiers"]:
        refs.update(modifier["source_refs"])
    return frozenset(refs)


def legal_v32_dynamic_action_keys_v1(reference_context: str) -> tuple[tuple[str, str], ...]:
    """Return the complete adjacent research-action grid for one intent state."""

    if reference_context not in REFERENCE_CONTEXTS:
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_CONTEXT_INVALID")
    return _LEGAL_ACTION_GRID[reference_context]


def _allocate_cluster_risk(
    *,
    reference_risk_budget: Decimal,
    raw_reference_risk_budget: Decimal,
    directional_subjective_tier_cap_units: Mapping[str, int],
    cluster_ids: Sequence[str],
    clusters: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Allocate quantized risk without letting one direction lift the other.

    LOW/HIGH units may split the already-scaled global envelope, but every
    direction remains bounded by its own ordinal cap against the raw envelope.
    """

    if reference_risk_budget < 0 or reference_risk_budget > Decimal("100"):
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_RISK_BUDGET_INVALID")
    if (
        raw_reference_risk_budget < reference_risk_budget
        or raw_reference_risk_budget < 0
        or raw_reference_risk_budget > Decimal("100")
    ):
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_RISK_BUDGET_INVALID")
    units_exact = reference_risk_budget / REFERENCE_RISK_QUANTUM
    raw_units_exact = raw_reference_risk_budget / REFERENCE_RISK_QUANTUM
    if (
        units_exact != units_exact.to_integral_value()
        or raw_units_exact != raw_units_exact.to_integral_value()
    ):
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_RISK_QUANTUM_INVALID")
    if (
        not isinstance(directional_subjective_tier_cap_units, Mapping)
        or set(directional_subjective_tier_cap_units) != {"LONG", "SHORT"}
    ):
        raise V32DynamicActionPlanError("V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID")
    directional_caps = {
        direction: _frozen_cap_units(
            directional_subjective_tier_cap_units[direction],
            "V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID",
        )
        for direction in ("LONG", "SHORT")
    }
    ordered = sorted(cluster_ids)
    if not ordered:
        if reference_risk_budget != 0:
            raise V32DynamicActionPlanError("V32_ACTION_RISK_WITHOUT_ELIGIBLE_CLUSTER")
        return []
    tiers: dict[str, str] = {}
    allocation_units: dict[str, int] = {}
    cluster_directions: dict[str, str] = {}
    for cluster_id in ordered:
        cluster = clusters.get(cluster_id)
        if cluster is None:
            raise V32DynamicActionPlanError("V32_ACTION_CLUSTER_REF_INVALID")
        tier = cluster["aggregate_tier"]
        units = TIER_ALLOCATION_UNITS.get(tier)
        if units is None or units <= 0:
            raise V32DynamicActionPlanError("V32_ACTION_CLUSTER_TIER_NOT_ELIGIBLE")
        direction = cluster.get("direction")
        if direction not in {"LONG", "SHORT"}:
            raise V32DynamicActionPlanError(
                "V32_ACTION_RISK_CLUSTER_DIRECTION_INVALID"
            )
        tiers[cluster_id] = tier
        allocation_units[cluster_id] = units
        cluster_directions[cluster_id] = direction

    def apportion(total: int, weights: Mapping[str, int]) -> dict[str, int]:
        denominator = sum(weights.values())
        if total < 0 or denominator <= 0:
            raise V32DynamicActionPlanError(
                "V32_ACTION_REFERENCE_RISK_BUDGET_INVALID"
            )
        result = {
            key: total * weight // denominator for key, weight in weights.items()
        }
        remainders = {
            key: total * weight % denominator for key, weight in weights.items()
        }
        missing = total - sum(result.values())
        for key in sorted(weights, key=lambda item: (-remainders[item], item))[
            :missing
        ]:
            result[key] += 1
        return result

    total_units = int(units_exact)
    raw_units = int(raw_units_exact)
    # Independent clusters may diversify the evidence lineage, but their count
    # is not directional confidence.  Summing cluster tiers here allowed an
    # Agent to increase one side's allocation merely by splitting the same
    # thesis into more clusters.  Direction-to-direction apportionment therefore
    # uses the strongest tier on each side; cluster weights are used only to
    # divide that already-fixed directional allocation within the side.
    direction_weights = {
        direction: max(
            (
                allocation_units[cluster_id]
                for cluster_id in ordered
                if cluster_directions[cluster_id] == direction
            ),
            default=0,
        )
        for direction in ("LONG", "SHORT")
    }
    direction_capacities = {
        direction: raw_units * directional_caps[direction] // 100
        if direction_weights[direction] > 0
        else 0
        for direction in ("LONG", "SHORT")
    }
    if total_units > sum(direction_capacities.values()):
        raise V32DynamicActionPlanError("V32_ACTION_DIRECTIONAL_RISK_CAP_INVALID")

    direction_allocations = {"LONG": 0, "SHORT": 0}
    remaining = total_units
    while remaining:
        active_weights = {
            direction: direction_weights[direction]
            for direction in ("LONG", "SHORT")
            if direction_weights[direction] > 0
            and direction_allocations[direction] < direction_capacities[direction]
        }
        if not active_weights:
            raise V32DynamicActionPlanError("V32_ACTION_DIRECTIONAL_RISK_CAP_INVALID")
        proposed = apportion(remaining, active_weights)
        added = 0
        for direction in active_weights:
            room = direction_capacities[direction] - direction_allocations[direction]
            increment = min(room, proposed[direction])
            direction_allocations[direction] += increment
            added += increment
        if added == 0:
            # This is reachable only when fewer quanta remain than active
            # directions.  Stable direction order is the deterministic tie-break.
            for direction in sorted(active_weights):
                if remaining == 0:
                    break
                if direction_allocations[direction] < direction_capacities[direction]:
                    direction_allocations[direction] += 1
                    remaining -= 1
            continue
        remaining -= added

    allocated_units: dict[str, int] = {}
    for direction in ("LONG", "SHORT"):
        direction_cluster_weights = {
            cluster_id: allocation_units[cluster_id]
            for cluster_id in ordered
            if cluster_directions[cluster_id] == direction
        }
        if not direction_cluster_weights:
            continue
        allocated_units.update(
            apportion(direction_allocations[direction], direction_cluster_weights)
        )
    return [
        {
            "cluster_id": cluster_id,
            "aggregate_tier": tiers[cluster_id],
            "allocation_units": allocation_units[cluster_id],
            "reference_risk": canonical_decimal(
                REFERENCE_RISK_QUANTUM * allocated_units[cluster_id]
            ),
        }
        for cluster_id in ordered
    ]


def _apply_path_modifier_risk_caps(
    *,
    allocations: Sequence[Mapping[str, Any]],
    eligible_risk_candidates: Sequence[Mapping[str, Any]],
    assessments: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Decimal]:
    cap_by_cluster: dict[str, int] = {}
    for candidate in eligible_risk_candidates:
        assessment = assessments[candidate["candidate_id"]]
        cap = int(assessment["risk_cap_units"])
        if cap <= 0:
            raise V32DynamicActionPlanError(
                "V32_ACTION_ZERO_PATH_MODIFIER_CAP_MUST_BLOCK_NEW_RISK"
            )
        for cluster_id in candidate["cluster_ids"]:
            if cluster_id in cap_by_cluster:
                raise V32DynamicActionPlanError(
                    "V32_ACTION_CLUSTER_RISK_DOUBLE_COUNTED"
                )
            cap_by_cluster[cluster_id] = cap

    result: list[dict[str, Any]] = []
    total = Decimal("0")
    for row in allocations:
        cluster_id = str(row["cluster_id"])
        cap = cap_by_cluster.get(cluster_id)
        if cap is None:
            raise V32DynamicActionPlanError(
                "V32_ACTION_PATH_MODIFIER_CLUSTER_CAP_MISSING"
            )
        pre_modifier = Decimal(str(row["reference_risk"]))
        capped = (
            (
                pre_modifier
                * Decimal(cap)
                / Decimal("100")
                / REFERENCE_RISK_QUANTUM
            ).to_integral_value(rounding=ROUND_FLOOR)
            * REFERENCE_RISK_QUANTUM
        )
        total += capped
        result.append(
            {
                "cluster_id": cluster_id,
                "aggregate_tier": row["aggregate_tier"],
                "allocation_units": row["allocation_units"],
                "pre_modifier_reference_risk": canonical_decimal(pre_modifier),
                "path_modifier_risk_cap_units": cap,
                "reference_risk": canonical_decimal(capped),
            }
        )
    return result, total


def compute_v32_effective_reference_risk_v1(
    *,
    raw_reference_risk_budget: Decimal | str,
    eligible_cluster_tiers: Sequence[str],
    eligible_cluster_directions: Sequence[str],
    residual_uncertainty_cap_units: int,
) -> dict[str, Any]:
    """Cap objective risk with an ordinal tier; tiers never add or amplify."""

    raw = _decimal(
        raw_reference_risk_budget, "V32_ACTION_REFERENCE_RISK_BUDGET_INVALID"
    )
    if raw != Decimal("1"):
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_RISK_ENVELOPE_INVALID")
    if isinstance(eligible_cluster_tiers, (str, bytes)) or not isinstance(
        eligible_cluster_tiers, Sequence
    ):
        raise V32DynamicActionPlanError("V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID")
    tiers = list(eligible_cluster_tiers)
    if isinstance(eligible_cluster_directions, (str, bytes)) or not isinstance(
        eligible_cluster_directions, Sequence
    ):
        raise V32DynamicActionPlanError("V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID")
    directions = list(eligible_cluster_directions)
    if len(directions) != len(tiers) or any(
        direction not in {"LONG", "SHORT"} for direction in directions
    ):
        raise V32DynamicActionPlanError("V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID")
    if any(tier not in SUBJECTIVE_PLAUSIBILITY_TIERS for tier in tiers):
        raise V32DynamicActionPlanError("V32_ACTION_SUBJECTIVE_TIER_CAP_INVALID")
    residual = _frozen_cap_units(
        residual_uncertainty_cap_units,
        "V32_ACTION_RISK_AVAILABILITY_INVALID",
    )
    directional_support = {
        direction: max(
            (
                SUBJECTIVE_TIER_RISK_CAP_UNITS[tier]
                for tier, cluster_direction in zip(tiers, directions, strict=True)
                if cluster_direction == direction
            ),
            default=0,
        )
        for direction in ("LONG", "SHORT")
    }
    absolute_support = max(directional_support.values(), default=0)
    bottleneck = min(absolute_support, residual)
    scaled = raw * Decimal(bottleneck) / Decimal(100)
    distributable = (
        (scaled / REFERENCE_RISK_QUANTUM).to_integral_value(rounding=ROUND_FLOOR)
        * REFERENCE_RISK_QUANTUM
    )
    return {
        "raw_reference_risk_budget": canonical_decimal(raw),
        "subjective_tier_cap_units": absolute_support,
        "directional_subjective_tier_cap_units": directional_support,
        "risk_bottleneck_cap_units": bottleneck,
        "effective_reference_risk_budget": canonical_decimal(distributable),
        "scaling_policy": (
            "MAX_TIER_WITHIN_DIRECTION_NO_SUM_MAX_OPPOSED_BRANCH_"
            "TIER_AND_RESIDUAL_CAP_ONLY_HARD_GATES_PRECEDING_NO_"
            "COVERAGE_REGIME_LIQUIDITY_OR_GEOMETRY_SCALAR"
        ),
    }


def _risk_availability(
    *,
    raw_budget: Decimal,
    eligible_risk_candidates: Sequence[Mapping[str, Any]],
    eligible_cluster_ids: Sequence[str],
    clusters: Mapping[str, Mapping[str, Any]],
    hypotheses: Mapping[str, Mapping[str, Any]],
    market_regime_state: Mapping[str, Any],
    current_pit_evidence_refs: frozenset[str],
) -> tuple[dict[str, Any], int, dict[str, int], str, int, int, Decimal]:
    """Derive evidence-chain diagnostics and the only lawful risk scalars.

    Hypothesis coverage is retained for diagnosis.  Source-admission coverage
    is unavailable in this state and therefore remains UNKNOWN; neither field
    can manufacture a risk scalar.  Typed regime and geometry checks are hard
    gates, while support tier and residual uncertainty are the only scalars.
    """

    eligible_hypothesis_ids = sorted(
        {
            hypothesis_id
            for cluster_id in eligible_cluster_ids
            for hypothesis_id in clusters[cluster_id]["member_hypothesis_ids"]
            if hypotheses[hypothesis_id]["status"]
            in ACTIONABLE_HYPOTHESIS_STATUSES
        }
    )
    coverage_missing: list[str] = []
    coverage_refs: set[str] = set()
    for hypothesis_id in eligible_hypothesis_ids:
        hypothesis = hypotheses[hypothesis_id]
        for field, requirement in (
            ("source_refs", "SOURCE"),
            ("supporting_refs", "SUPPORT"),
            ("opposing_refs", "COUNTER"),
        ):
            refs = hypothesis[field]
            coverage_refs.update(refs)
            if not refs:
                coverage_missing.append(f"{hypothesis_id}:{requirement}")
    if not eligible_hypothesis_ids:
        coverage_missing.append("NO_ELIGIBLE_HYPOTHESIS")

    normalized = {
        "derivation_policy": (
            "DETERMINISTIC_HYPOTHESIS_EVIDENCE_CHAIN_DIAGNOSTIC_AND_TYPED_"
            "HARD_GATES_NO_AGENT_QUALITY_OR_ATTRACTIVENESS_SCALAR"
        ),
        "hypothesis_evidence_chain_coverage": (
            "COMPLETE" if not coverage_missing else "INCOMPLETE"
        ),
        "hypothesis_evidence_refs": sorted(coverage_refs),
        "missing_hypothesis_evidence_requirements": sorted(coverage_missing),
        "source_admission_coverage_status": "UNKNOWN_NOT_IN_DYNAMIC_STATE",
        "regime_gate_status": (
            "NONDIRECTIONAL_ZERO_RISK"
            if market_regime_state["regime"]
            in CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES
            else "ALLOWED_NO_EXTRA_SCALAR"
        ),
        "geometry_gate_status": (
            "PASSED_BY_TYPED_CANDIDATE_AND_TRANCHE_VALIDATION"
            if eligible_risk_candidates
            else "NO_ELIGIBLE_RISK_CANDIDATE"
        ),
    }
    if not coverage_refs.issubset(current_pit_evidence_refs):
        raise V32DynamicActionPlanError(
            "V32_ACTION_DERIVED_RISK_EVIDENCE_NOT_IN_CURRENT_STATE_PIT_CHAIN"
        )
    residual_tiers = [
        hypothesis["subjective_plausibility_tier"]
        for hypothesis in hypotheses.values()
        if hypothesis["direction"] in {"OTHER", "UNKNOWN"}
    ]
    if len(residual_tiers) != 2:
        raise V32DynamicActionPlanError("V32_ACTION_RESIDUAL_SUPPORT_INVALID")
    residual_uncertainty_tier = max(
        residual_tiers, key=lambda tier: SUBJECTIVE_TIER_ORDER[tier]
    )
    residual_clarity = 100 - SUBJECTIVE_TIER_RISK_CAP_UNITS[
        residual_uncertainty_tier
    ]
    effective = compute_v32_effective_reference_risk_v1(
        raw_reference_risk_budget=raw_budget,
        eligible_cluster_tiers=[
            clusters[cluster_id]["aggregate_tier"]
            for cluster_id in eligible_cluster_ids
        ],
        eligible_cluster_directions=[
            clusters[cluster_id]["direction"] for cluster_id in eligible_cluster_ids
        ],
        residual_uncertainty_cap_units=residual_clarity,
    )
    absolute_support = effective["subjective_tier_cap_units"]
    directional_support = effective["directional_subjective_tier_cap_units"]
    bottleneck = effective["risk_bottleneck_cap_units"]
    distributable = Decimal(effective["effective_reference_risk_budget"])
    if not eligible_cluster_ids and distributable != 0:
        raise V32DynamicActionPlanError("V32_ACTION_RISK_WITHOUT_ELIGIBLE_CLUSTER")
    return (
        normalized,
        absolute_support,
        directional_support,
        residual_uncertainty_tier,
        residual_clarity,
        bottleneck,
        distributable,
    )


def _inactivity_watchdog(
    row: Any,
    *,
    as_of: datetime,
    expires_at: datetime,
    candidate_ids: set[str],
    risk_candidate_ids: set[str],
) -> dict[str, Any]:
    code = "V32_ACTION_WATCHDOG_INVALID"
    if not isinstance(row, Mapping) or set(row) != _WATCHDOG_FIELDS:
        raise V32DynamicActionPlanError(code)
    inactivity_text = _time(row["inactivity_since"], code)
    inactivity_since = _moment(inactivity_text, code)
    if inactivity_since > as_of:
        raise V32DynamicActionPlanError(code)
    model_inactivity_text = _time(row["model_adaptation_inactivity_since"], code)
    model_inactivity_since = _moment(model_inactivity_text, code)
    if model_inactivity_since > as_of:
        raise V32DynamicActionPlanError(code)
    consecutive = row["consecutive_wait_cycles"]
    model_consecutive = row["consecutive_model_stale_cycles"]
    maximum_cycles = row["max_wait_cycles_before_review"]
    maximum_seconds = row["max_inactivity_seconds"]
    if (
        isinstance(consecutive, bool)
        or not isinstance(consecutive, int)
        or consecutive < 0
        or isinstance(model_consecutive, bool)
        or not isinstance(model_consecutive, int)
        or model_consecutive < 0
        or isinstance(maximum_cycles, bool)
        or not isinstance(maximum_cycles, int)
        or maximum_cycles < 1
        or isinstance(maximum_seconds, bool)
        or not isinstance(maximum_seconds, int)
        or maximum_seconds < 60
    ):
        raise V32DynamicActionPlanError(code)
    if (
        maximum_cycles != CURRENT_PILOT_WATCHDOG_MAX_WAIT_CYCLES
        or maximum_seconds != CURRENT_PILOT_WATCHDOG_MAX_INACTIVITY_SECONDS
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_WATCHDOG_PILOT_THRESHOLD_INVALID"
        )
    risk_due = consecutive >= maximum_cycles or (
        as_of - inactivity_since
    ).total_seconds() >= maximum_seconds
    model_due = model_consecutive >= maximum_cycles or (
        as_of - model_inactivity_since
    ).total_seconds() >= maximum_seconds
    due = risk_due or model_due
    if (
        row["testable_risk_plan_review_due"] is not risk_due
        or row["model_adaptation_review_due"] is not model_due
        or row["forced_review_due"] is not due
    ):
        raise V32DynamicActionPlanError("V32_ACTION_WATCHDOG_DUE_MISMATCH")
    required = _strings(row["required_responses"], code, allow_empty=not due)
    baseline_refs = _strings(
        row["baseline_comparison_refs"], code, allow_empty=not due
    )
    shadow_candidates = _strings(
        row["shadow_plan_candidate_ids"], code, allow_empty=not due
    )
    if any(item not in candidate_ids for item in shadow_candidates):
        raise V32DynamicActionPlanError("V32_ACTION_WATCHDOG_SHADOW_REF_INVALID")
    if due:
        if set(required) != set(WATCHDOG_REQUIRED_RESPONSES):
            raise V32DynamicActionPlanError(
                "V32_ACTION_WATCHDOG_RESPONSE_SET_INCOMPLETE"
            )
        if not set(shadow_candidates).intersection(risk_candidate_ids):
            raise V32DynamicActionPlanError(
                "V32_ACTION_WATCHDOG_RISK_SHADOW_PLAN_REQUIRED"
            )
    elif required or baseline_refs or shadow_candidates:
        raise V32DynamicActionPlanError("V32_ACTION_WATCHDOG_PREMATURE_RESPONSE")
    review_text = _time(row["next_watchdog_review_at"], code)
    if not as_of < _moment(review_text, code) <= expires_at:
        raise V32DynamicActionPlanError("V32_ACTION_WATCHDOG_REVIEW_TIME_INVALID")
    if (
        row["forces_action"] is not False
        or row["shadow_plan_scope"]
        != "CONDITIONAL_RESEARCH_COMPARISON_NO_FILL_OR_FORCED_ENTRY"
        or row["clock_semantics"]
        != (
            "DUAL_DURABLE_CLOCKS_TESTABLE_RISK_PLAN_AND_MODEL_ADAPTATION_"
            "NEITHER_IS_REAL_EXPOSURE"
        )
        or row["real_exposure_claim"] != "NONE_RESEARCH_PLAN_ONLY"
    ):
        raise V32DynamicActionPlanError("V32_ACTION_WATCHDOG_FORCED_ENTRY_FORBIDDEN")
    return {
        "inactivity_since": inactivity_text,
        "consecutive_wait_cycles": consecutive,
        "testable_risk_plan_review_due": risk_due,
        "model_adaptation_inactivity_since": model_inactivity_text,
        "consecutive_model_stale_cycles": model_consecutive,
        "model_adaptation_review_due": model_due,
        "max_wait_cycles_before_review": maximum_cycles,
        "max_inactivity_seconds": maximum_seconds,
        "forced_review_due": due,
        "required_responses": required,
        "baseline_comparison_refs": baseline_refs,
        "shadow_plan_candidate_ids": shadow_candidates,
        "next_watchdog_review_at": review_text,
        "forces_action": False,
        "shadow_plan_scope": "CONDITIONAL_RESEARCH_COMPARISON_NO_FILL_OR_FORCED_ENTRY",
        "clock_semantics": (
            "DUAL_DURABLE_CLOCKS_TESTABLE_RISK_PLAN_AND_MODEL_ADAPTATION_"
            "NEITHER_IS_REAL_EXPOSURE"
        ),
        "real_exposure_claim": "NONE_RESEARCH_PLAN_ONLY",
    }


def _future_execution_hazard(row: Any) -> dict[str, Any]:
    code = "V32_ACTION_EXECUTION_HAZARD_INVALID"
    if not isinstance(row, Mapping) or set(row) != _EXECUTION_HAZARD_FIELDS:
        raise V32DynamicActionPlanError(code)
    latency = row["future_latency_bound_ms"]
    latency_refs = _strings(row["latency_evidence_refs"], code, allow_empty=True)
    if (
        latency is not None
        or row["latency_qualification_status"] != "UNKNOWN_NOT_QUALIFIED"
        or latency_refs
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_LATENCY_BOUND_NOT_QUALIFIED_FOR_CURRENT_PILOT"
        )
    if (
        row["model_scope"] != "FUTURE_EXECUTION_HAZARD_ONLY"
        or row["stop_semantics"]
        != "STOP_TRIGGER_IS_NOT_FILL_GAP_SLIPPAGE_REJECTION_REMAIN"
        or row["current_order_claim"] != "NONE_NO_CURRENT_ORDER"
        or row["current_protection_claim"] != "NONE_NO_CURRENT_PROTECTION"
        or row["unbounded_venue_outage_status"]
        != "UNKNOWN_MAX_LOSS_BLOCKS_FUTURE_EXECUTION"
        or row["guaranteed_exit_price"] is not False
    ):
        raise V32DynamicActionPlanError("V32_ACTION_EXECUTION_HAZARD_OVERCLAIM")
    scenarios = _strings(row["required_scenarios"], code)
    controls = _strings(row["future_execution_control_requirements"], code)
    if scenarios != list(REQUIRED_EXECUTION_HAZARD_SCENARIOS):
        raise V32DynamicActionPlanError(
            "V32_ACTION_EXECUTION_HAZARD_SCENARIOS_INCOMPLETE"
        )
    if controls != list(FUTURE_EXECUTION_CONTROL_REQUIREMENTS):
        raise V32DynamicActionPlanError(
            "V32_ACTION_EXECUTION_HAZARD_CONTROLS_INCOMPLETE"
        )
    return {
        "hazard_id": _text(row["hazard_id"], code),
        "future_latency_bound_ms": None,
        "latency_qualification_status": "UNKNOWN_NOT_QUALIFIED",
        "latency_evidence_refs": [],
        "network_failure_scenario": _text(row["network_failure_scenario"], code),
        "required_scenarios": scenarios,
        "future_execution_control_requirements": controls,
        "unbounded_venue_outage_status": (
            "UNKNOWN_MAX_LOSS_BLOCKS_FUTURE_EXECUTION"
        ),
        "guaranteed_exit_price": False,
        "model_scope": "FUTURE_EXECUTION_HAZARD_ONLY",
        "stop_semantics": "STOP_TRIGGER_IS_NOT_FILL_GAP_SLIPPAGE_REJECTION_REMAIN",
        "current_order_claim": "NONE_NO_CURRENT_ORDER",
        "current_protection_claim": "NONE_NO_CURRENT_PROTECTION",
    }


def _candidate_path_modifier_assessment(
    candidate: Mapping[str, Any],
    *,
    hypotheses: Mapping[str, Mapping[str, Any]],
    zones: Mapping[str, Mapping[str, Any]],
    modifiers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive a deterministic risk cap without turning modifiers into odds.

    A modifier is an external path condition, not another directional vote.
    It can leave risk unchanged, cap it, or invalidate a path, but can never
    increase support.  Expired/falsified modifiers remain in the audit trail
    and have no current risk effect.  An UNKNOWN modifier is capped at 50 so
    uncertainty cannot silently behave like confirmed support.
    """

    # A zone is part of the candidate's causal/risk path, not decorative
    # metadata.  Therefore its modifiers join the hypothesis modifiers under
    # a closed union.  A caller cannot omit a stop-run condition merely by
    # selecting a hypothesis whose own modifier list is empty.
    applicable_ids = sorted(
        {
            modifier_id
            for hypothesis_id in candidate["hypothesis_ids"]
            for modifier_id in hypotheses[hypothesis_id]["path_modifier_ids"]
        }
        | {
            modifier_id
            for zone_id in candidate["zone_ids"]
            for modifier_id in zones[zone_id]["path_modifier_ids"]
        }
    )
    if any(modifier_id not in modifiers for modifier_id in applicable_ids):
        raise V32DynamicActionPlanError("V32_ACTION_PATH_MODIFIER_REF_INVALID")
    active_ids = [
        modifier_id
        for modifier_id in applicable_ids
        if modifiers[modifier_id]["status"] in {"ACTIVE", "UNKNOWN"}
    ]
    invalidating_ids = [
        modifier_id
        for modifier_id in active_ids
        if modifiers[modifier_id]["status"] == "ACTIVE"
        and modifiers[modifier_id]["effect"] == "INVALIDATES_PATH"
    ]
    caps: list[int] = []
    for modifier_id in active_ids:
        modifier = modifiers[modifier_id]
        cap = PATH_MODIFIER_RISK_CAPS[modifier["effect"]]
        if modifier["status"] == "UNKNOWN":
            cap = UNKNOWN_PATH_MODIFIER_RISK_CAP
        caps.append(cap)
    return {
        "candidate_id": candidate["candidate_id"],
        "applicable_modifier_ids": applicable_ids,
        "active_modifier_ids": active_ids,
        "invalidating_modifier_ids": invalidating_ids,
        "risk_cap_units": min(caps, default=100),
        "risk_effect_policy": (
            "NO_SUPPORT_INFLATION_MIN_ACTIVE_EFFECT_CAP_UNKNOWN_AT_50_"
            "ACTIVE_INVALIDATION_BLOCKS_NEW_RISK"
        ),
    }


def _current_execution_gate(
    hazard: Mapping[str, Any],
) -> dict[str, Any]:
    """Make the present non-executable boundary machine-readable.

    Stress buffers can model ordinary slippage and a bounded gap, but an
    unbounded venue outage cannot be converted into a guaranteed stop fill.
    Consequently every current research plan has zero executable risk even
    while its conditional candidates remain available for comparison.
    """

    if hazard["unbounded_venue_outage_status"] != (
        "UNKNOWN_MAX_LOSS_BLOCKS_FUTURE_EXECUTION"
    ):
        raise V32DynamicActionPlanError("V32_ACTION_EXECUTION_GATE_INVALID")
    return {
        "current_execution_eligibility": "BLOCKED_PUBLIC_RESEARCH_ONLY",
        "block_reasons": [
            "NO_EXTERNAL_EXECUTION_AUTHORITY",
            "UNBOUNDED_VENUE_OUTAGE_MAX_LOSS_UNKNOWN",
        ],
        "research_candidates_remain_comparable": True,
        "order_submission_allowed": False,
        "stop_trigger_is_fill": False,
        "unbounded_venue_outage_resolved": False,
        "required_future_controls": list(FUTURE_EXECUTION_CONTROL_REQUIREMENTS),
    }


def _reference_tranche_state(
    row: Any, *, reference_context: str, as_of: datetime
) -> dict[str, Any]:
    """Normalize the sole research-intent parent carried between cycles."""

    code = "V32_ACTION_REFERENCE_TRANCHE_STATE_INVALID"
    if not isinstance(row, Mapping) or set(row) != _REFERENCE_TRANCHE_STATE_FIELDS:
        raise V32DynamicActionPlanError(code)
    status = _text(row["status"], code)
    tranche_id = _nullable_id(row["tranche_id"], code)
    direction = _text(row["direction"], code)
    entry = _nullable_decimal(row["entry_reference"], code)
    stop = _nullable_decimal(row["protective_stop_reference"], code)
    valid_until_text = _nullable_time(row["valid_until"], code)
    valid_until = (
        _moment(valid_until_text, code) if valid_until_text is not None else None
    )
    hypothesis_ids = _strings(
        row["supporting_hypothesis_ids"], code, allow_empty=True
    )
    cluster_ids = _strings(
        row["supporting_cluster_ids"], code, allow_empty=True
    )
    zone_ids = _strings(row["zone_ids"], code, allow_empty=True)
    context_direction = (
        "LONG"
        if reference_context == "LONG_RESEARCH_INTENT"
        else "SHORT" if reference_context == "SHORT_RESEARCH_INTENT" else None
    )
    if status == "NONE":
        if (
            tranche_id is not None
            or direction != "NONE"
            or entry is not None
            or stop is not None
            or valid_until is not None
            or hypothesis_ids
            or cluster_ids
            or zone_ids
            or context_direction is not None
        ):
            raise V32DynamicActionPlanError(code)
        return {
            "status": "NONE",
            "tranche_id": None,
            "direction": "NONE",
            "entry_reference": None,
            "protective_stop_reference": None,
            "valid_until": None,
            "supporting_hypothesis_ids": [],
            "supporting_cluster_ids": [],
            "zone_ids": [],
        }
    if (
        status != "ACTIVE"
        or tranche_id is None
        or direction != context_direction
        or entry is None
        or stop is None
        or valid_until is None
        or not hypothesis_ids
        or not cluster_ids
        or not zone_ids
        or entry <= 0
        or stop <= 0
        or valid_until <= as_of
        or (direction == "LONG" and stop >= entry)
        or (direction == "SHORT" and stop <= entry)
    ):
        raise V32DynamicActionPlanError(code)
    return {
        "status": "ACTIVE",
        "tranche_id": tranche_id,
        "direction": direction,
        "entry_reference": canonical_decimal(entry),
        "protective_stop_reference": canonical_decimal(stop),
        "valid_until": valid_until_text,
        "supporting_hypothesis_ids": hypothesis_ids,
        "supporting_cluster_ids": cluster_ids,
        "zone_ids": zone_ids,
    }


def _derive_research_breakout_trigger_pairs(
    *,
    run_id: str,
    cycle_index: int,
    as_of: str,
    regime_is_nondirectional: bool,
    candidates: Sequence[Mapping[str, Any]],
    zones: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Derive one sealed research-only breakout pair for a zero-risk regime.

    This is not Agent-authored order logic. It binds the two legal directional
    research paths to exact typed zone boundaries and can only request a fresh
    analysis after a future public 15-minute bar closes. It cannot unlock
    risk, submit an order, or claim an OCO facility.
    """

    if not regime_is_nondirectional:
        return []
    risk_candidates = [
        candidate
        for candidate in candidates
        if candidate["action_kind"] in RISK_INCREASING_ACTIONS
    ]
    by_direction = {
        direction: [
            candidate
            for candidate in risk_candidates
            if candidate["direction"] == direction
        ]
        for direction in ("LONG", "SHORT")
    }
    if any(len(by_direction[direction]) != 1 for direction in by_direction):
        raise V32DynamicActionPlanError(
            "V32_ACTION_NONDIRECTIONAL_TRIGGER_DIRECTION_COVERAGE_INVALID"
        )
    long_candidate = by_direction["LONG"][0]
    short_candidate = by_direction["SHORT"][0]
    if any(
        len(candidate["zone_ids"]) != 1
        for candidate in (long_candidate, short_candidate)
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_NONDIRECTIONAL_TRIGGER_SINGLE_ZONE_REQUIRED"
        )
    long_zone_id = long_candidate["zone_ids"][0]
    short_zone_id = short_candidate["zone_ids"][0]
    long_threshold = Decimal(zones[long_zone_id]["upper_bound"])
    short_threshold = Decimal(zones[short_zone_id]["lower_bound"])
    if long_threshold <= short_threshold:
        raise V32DynamicActionPlanError(
            "V32_ACTION_NONDIRECTIONAL_TRIGGER_THRESHOLDS_OVERLAP"
        )
    expires_at = min(
        (long_candidate["horizon_at"], short_candidate["horizon_at"]),
        key=lambda value: _moment(
            value, "V32_ACTION_NONDIRECTIONAL_TRIGGER_TIME_INVALID"
        ),
    )
    pair = {
        "schema_id": "theory_paper_v32_research_breakout_trigger_pair_v1",
        "schema_version": "1.0.0",
        "pair_id": (
            f"research-breakout::{run_id}::{cycle_index}::"
            f"{long_zone_id}::{short_zone_id}"
        ),
        "source_component_id": "CLOSED_CANDLES_15M",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "timeframe": "15M",
        "observed_field": "close",
        "closed_bar_required": True,
        "required_consecutive_closed_bars": 1,
        "valid_from": as_of,
        "expires_at": expires_at,
        "pit_rule": (
            "BAR_CLOSE_AFTER_VALID_FROM_AND_VERIFIED_BUNDLE_AVAILABLE_BY_"
            "REANALYSIS"
        ),
        "resolution_policy": (
            "FIRST_MATCH_RETIRES_PAIR_AND_REQUIRES_FRESH_REANALYSIS"
        ),
        "match_effect": (
            "RESEARCH_REANALYSIS_ONLY_NO_AUTOMATIC_ACTION_OR_RISK"
        ),
        "status": "UNOBSERVED_AT_PLAN_SEAL",
        "legs": [
            {
                "candidate_id": long_candidate["candidate_id"],
                "direction": "LONG",
                "zone_id": long_zone_id,
                "boundary_field": "upper_bound",
                "threshold_value": canonical_decimal(long_threshold),
                "comparator": "CLOSE_GT_THRESHOLD",
            },
            {
                "candidate_id": short_candidate["candidate_id"],
                "direction": "SHORT",
                "zone_id": short_zone_id,
                "boundary_field": "lower_bound",
                "threshold_value": canonical_decimal(short_threshold),
                "comparator": "CLOSE_LT_THRESHOLD",
            },
        ],
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "order_claim": "NONE_NO_ORDER",
        "oco_claim": "NONE_NO_OCO_ORDER",
        "executable": False,
    }
    if set(pair) != _RESEARCH_BREAKOUT_TRIGGER_PAIR_FIELDS or any(
        set(leg) != _RESEARCH_BREAKOUT_TRIGGER_LEG_FIELDS
        for leg in pair["legs"]
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_NONDIRECTIONAL_TRIGGER_INTERNAL_INVALID"
        )
    return [pair]


def _candidate(
    row: Any,
    *,
    as_of: datetime,
    expires_at: datetime,
    hypotheses: Mapping[str, Mapping[str, Any]],
    clusters: Mapping[str, Mapping[str, Any]],
    zones: Mapping[str, Mapping[str, Any]],
    unknowns: Mapping[str, Mapping[str, Any]],
    modifiers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    code = "V32_ACTION_CANDIDATE_INVALID"
    if not isinstance(row, Mapping) or set(row) != _CANDIDATE_FIELDS:
        raise V32DynamicActionPlanError(code)
    action = _text(row["action_kind"], code)
    direction = _text(row["direction"], code)
    state = _text(row["plan_state"], code)
    feasibility = _text(row["feasibility"], code)
    block_reason = _text(row["block_reason"], code)
    if (
        action not in ACTION_KINDS
        or direction not in ACTION_DIRECTIONS
        or state != "CONDITIONAL"
        or feasibility not in FEASIBILITY_STATES
        or block_reason not in BLOCK_REASONS
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_CANDIDATE_PLAN_STATE_INVALID"
            if state != "CONDITIONAL"
            else code
        )
    horizon_text = _time(row["horizon_at"], "V32_ACTION_HORIZON_INVALID")
    horizon = _moment(horizon_text, "V32_ACTION_HORIZON_INVALID")
    if not as_of < horizon <= expires_at:
        raise V32DynamicActionPlanError("V32_ACTION_HORIZON_INVALID")

    blocking_unknown_ids = _strings(
        row["blocking_unknown_ids"], code, allow_empty=True
    )
    blocking_refs = _strings(row["blocking_evidence_refs"], code, allow_empty=True)
    if feasibility == "ELIGIBLE":
        if block_reason != "NONE" or blocking_unknown_ids or blocking_refs:
            raise V32DynamicActionPlanError("V32_ACTION_ELIGIBLE_BLOCK_FIELDS_INVALID")
    else:
        if block_reason == "NONE" or not blocking_refs:
            raise V32DynamicActionPlanError("V32_ACTION_BLOCK_REASON_REQUIRED")
        if block_reason == "MAX_LOSS":
            # This plan has no position or order authority.  Unknown real
            # execution loss is an instrument-wide future-executor gate, not
            # a switch for deleting one current research direction.
            raise V32DynamicActionPlanError(
                "V32_ACTION_REAL_EXECUTION_MAX_LOSS_CANNOT_BLOCK_RESEARCH"
            )
        if block_reason == "FACT_INTEGRITY":
            expected_type = "UNKNOWN_FACT_INTEGRITY"
            if not blocking_unknown_ids or any(
                unknown_id not in unknowns
                or unknowns[unknown_id]["unknown_type"] != expected_type
                for unknown_id in blocking_unknown_ids
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_HARD_BLOCK_UNKNOWN_BINDING_INVALID"
                )
        elif blocking_unknown_ids:
            raise V32DynamicActionPlanError(
                "V32_ACTION_NON_HARD_BLOCK_UNKNOWN_BINDING_INVALID"
            )

    hypothesis_ids = _strings(row["hypothesis_ids"], code, allow_empty=action == "WAIT")
    cluster_ids = _strings(row["cluster_ids"], code, allow_empty=action == "WAIT")
    zone_ids = _strings(row["zone_ids"], code, allow_empty=action == "WAIT")
    if any(item not in hypotheses for item in hypothesis_ids):
        raise V32DynamicActionPlanError("V32_ACTION_HYPOTHESIS_REF_INVALID")
    if any(item not in clusters for item in cluster_ids):
        raise V32DynamicActionPlanError("V32_ACTION_CLUSTER_REF_INVALID")
    if any(item not in zones for item in zone_ids):
        raise V32DynamicActionPlanError("V32_ACTION_ZONE_REF_INVALID")
    if action in RISK_INCREASING_ACTIONS and any(
        clusters[item]["direction"] != direction for item in cluster_ids
    ):
        raise V32DynamicActionPlanError("V32_ACTION_RISK_CLUSTER_DIRECTION_INVALID")
    if action in RISK_INCREASING_ACTIONS and any(
        hypotheses[item]["status"] not in ACTIONABLE_HYPOTHESIS_STATUSES
        for item in hypothesis_ids
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_TERMINAL_HYPOTHESIS_CANNOT_SUPPORT_NEW_RISK"
        )
    if action == "HOLD" and any(
        clusters[item]["direction"] != direction for item in cluster_ids
    ):
        raise V32DynamicActionPlanError("V32_ACTION_HOLD_CLUSTER_DIRECTION_INVALID")
    if action in RISK_INCREASING_ACTIONS:
        actionable_cluster_hypothesis_ids = {
            hypothesis_id
            for cluster_id in cluster_ids
            for hypothesis_id in clusters[cluster_id]["member_hypothesis_ids"]
            if hypotheses[hypothesis_id]["status"]
            in ACTIONABLE_HYPOTHESIS_STATUSES
        }
        if (
            set(hypothesis_ids) != actionable_cluster_hypothesis_ids
            or any(
                hypotheses[hypothesis_id]["direction"] != direction
                for hypothesis_id in hypothesis_ids
            )
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_RISK_CLUSTER_HYPOTHESIS_BINDING_INVALID"
            )
    if action in RISK_INCREASING_ACTIONS:
        earliest_hypothesis_expiry = min(
            _moment(
                hypotheses[item]["expires_at"],
                "V32_ACTION_HYPOTHESIS_EXPIRY_INVALID",
            )
            for item in hypothesis_ids
        )
        if horizon > earliest_hypothesis_expiry:
            raise V32DynamicActionPlanError(
                "V32_ACTION_HORIZON_EXCEEDS_SUPPORTING_HYPOTHESIS_EXPIRY"
            )
    if zone_ids:
        zone_expiries = [
            _moment(zones[item]["expires_at"], "V32_ACTION_ZONE_EXPIRY_INVALID")
            for item in zone_ids
        ]
        if any(expiry <= as_of for expiry in zone_expiries):
            raise V32DynamicActionPlanError(
                "V32_ACTION_RETIRED_ZONE_CANNOT_SUPPORT_CANDIDATE"
            )
        if action in RISK_INCREASING_ACTIONS and horizon > min(zone_expiries):
            raise V32DynamicActionPlanError(
                "V32_ACTION_HORIZON_EXCEEDS_SUPPORTING_ZONE_EXPIRY"
            )

    candidate_support_dependencies: set[str] = set()
    for hypothesis_id in hypothesis_ids:
        candidate_support_dependencies.update(
            hypotheses[hypothesis_id]["dependency_groups"]
        )
    for cluster_id in cluster_ids:
        candidate_support_dependencies.update(
            clusters[cluster_id]["shared_dependency_groups"]
        )
    for zone_id in zone_ids:
        zone = zones[zone_id]
        if not (
            set(hypothesis_ids).intersection(
                zone["path_hypothesis_ids"].values()
            )
            or candidate_support_dependencies.intersection(
                zone["dependency_groups"]
            )
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_ZONE_SUPPORT_BINDING_INVALID"
            )
    candidate_dependencies = set(candidate_support_dependencies)
    for zone_id in zone_ids:
        candidate_dependencies.update(zones[zone_id]["dependency_groups"])
    fact_integrity_blockers = sorted(
        unknown_id
        for unknown_id, unknown in unknowns.items()
        if unknown["unknown_type"] == "UNKNOWN_FACT_INTEGRITY"
        and candidate_dependencies.intersection(unknown["dependency_refs"])
    )
    applicable_modifier_ids = sorted(
        {
            modifier_id
            for hypothesis_id in hypothesis_ids
            for modifier_id in hypotheses[hypothesis_id]["path_modifier_ids"]
        }
        | {
            modifier_id
            for zone_id in zone_ids
            for modifier_id in zones[zone_id]["path_modifier_ids"]
        }
    )
    if any(modifier_id not in modifiers for modifier_id in applicable_modifier_ids):
        raise V32DynamicActionPlanError("V32_ACTION_PATH_MODIFIER_REF_INVALID")
    active_invalidating_modifiers = [
        modifiers[modifier_id]
        for modifier_id in applicable_modifier_ids
        if modifiers[modifier_id]["status"] == "ACTIVE"
        and modifiers[modifier_id]["effect"] == "INVALIDATES_PATH"
    ]
    invalidation_refs = {
        source_ref
        for modifier in active_invalidating_modifiers
        for source_ref in modifier["source_refs"]
    }
    extreme_tier_cluster_ids = [
        cluster_id
        for cluster_id in cluster_ids
        if clusters[cluster_id]["aggregate_tier"] == "EXTREME_UNCERTAINTY"
    ]
    if action in RISK_INCREASING_ACTIONS:
        if fact_integrity_blockers:
            expected_reason = "FACT_INTEGRITY"
            expected_unknowns = fact_integrity_blockers
            expected_refs = {
                ref
                for unknown_id in fact_integrity_blockers
                for ref in unknowns[unknown_id]["dependency_refs"]
            } | invalidation_refs
        elif active_invalidating_modifiers:
            expected_reason = "PATH_MODIFIER_INVALIDATION"
            expected_unknowns = []
            expected_refs = invalidation_refs
        elif extreme_tier_cluster_ids:
            expected_reason = "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY"
            expected_unknowns = []
            expected_refs = {
                ref
                for cluster_id in extreme_tier_cluster_ids
                for hypothesis_id in clusters[cluster_id]["member_hypothesis_ids"]
                for ref in hypotheses[hypothesis_id]["source_refs"]
            }
        else:
            expected_reason = None
            expected_unknowns = []
            expected_refs = set()
        if expected_reason is not None:
            if (
                feasibility != "BLOCKED"
                or block_reason != expected_reason
                or blocking_unknown_ids != expected_unknowns
                or blocking_refs != sorted(expected_refs)
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_DERIVED_HARD_GATE_MUST_BLOCK_NEW_RISK"
                )
        elif block_reason in {
            "FACT_INTEGRITY",
            "PATH_MODIFIER_INVALIDATION",
            "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
        }:
            raise V32DynamicActionPlanError(
                "V32_ACTION_HARD_GATE_BLOCK_WITHOUT_DEPENDENT_CAUSE"
            )

    risk_tranche_id = _nullable_id(row["risk_tranche_id"], code)
    parent_tranche_id = _nullable_id(row["parent_tranche_id"], code)
    close_first = _nullable_id(row["close_first_candidate_id"], code)
    reentry_id = _nullable_id(row["reentry_obligation_id"], code)
    new_evidence = _strings(row["new_evidence_refs"], code, allow_empty=True)

    if action == "WAIT":
        if (
            direction != "NONE"
            or feasibility != "ELIGIBLE"
            or any((risk_tranche_id, parent_tranche_id, close_first, reentry_id))
            or hypothesis_ids
            or cluster_ids
            or zone_ids
            or new_evidence
        ):
            raise V32DynamicActionPlanError("V32_ACTION_WAIT_CANDIDATE_INVALID")
    elif direction == "NONE":
        raise V32DynamicActionPlanError("V32_ACTION_DIRECTION_REQUIRED")

    if action in RISK_INCREASING_ACTIONS:
        if (feasibility == "ELIGIBLE") != (risk_tranche_id is not None):
            raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_BINDING_INVALID")
    elif risk_tranche_id is not None:
        raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_FORBIDDEN")

    if action == "OPEN_PROBE":
        if any((parent_tranche_id, close_first, reentry_id)):
            raise V32DynamicActionPlanError("V32_ACTION_OPEN_PARENT_INVALID")
    elif action == "ADD":
        if parent_tranche_id is None or close_first is not None or reentry_id is not None:
            raise V32DynamicActionPlanError("V32_ACTION_ADD_PARENT_INVALID")
        if feasibility == "ELIGIBLE" and not new_evidence:
            raise V32DynamicActionPlanError("V32_ACTION_ADD_NEW_EVIDENCE_REQUIRED")
    elif action in {"HOLD", "REDUCE", "CLOSE"}:
        if parent_tranche_id is None or any((close_first, reentry_id)):
            raise V32DynamicActionPlanError("V32_ACTION_MANAGEMENT_PARENT_INVALID")
    elif action == "REENTER":
        if reentry_id is None or any((parent_tranche_id, close_first)):
            raise V32DynamicActionPlanError("V32_ACTION_REENTRY_OBLIGATION_REQUIRED")
        if feasibility == "ELIGIBLE" and not new_evidence:
            raise V32DynamicActionPlanError("V32_ACTION_REENTRY_NEW_EVIDENCE_REQUIRED")
    elif action == "REVERSE":
        if parent_tranche_id is None or close_first is None or reentry_id is not None:
            raise V32DynamicActionPlanError("V32_ACTION_REVERSE_SEQUENCE_INVALID")
        if feasibility == "ELIGIBLE" and not new_evidence:
            raise V32DynamicActionPlanError("V32_ACTION_REVERSE_NEW_EVIDENCE_REQUIRED")

    if block_reason == "NO_NEW_EVIDENCE":
        if (
            action not in {"ADD", "REENTER", "REVERSE"}
            or feasibility != "BLOCKED"
            or new_evidence
            or blocking_unknown_ids
            or blocking_refs != [NO_NEW_CURRENT_PIT_EVIDENCE_REF]
            or risk_tranche_id is not None
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_NO_NEW_EVIDENCE_BLOCK_INVALID"
            )

    return {
        "candidate_id": _text(row["candidate_id"], code),
        "action_kind": action,
        "direction": direction,
        "plan_state": state,
        "feasibility": feasibility,
        "block_reason": block_reason,
        "blocking_unknown_ids": blocking_unknown_ids,
        "blocking_evidence_refs": blocking_refs,
        "trigger_conditions": _strings(row["trigger_conditions"], code),
        "guard_conditions": _strings(row["guard_conditions"], code),
        "invalidation_conditions": _strings(row["invalidation_conditions"], code),
        "horizon_at": horizon_text,
        "next_observation": _text(row["next_observation"], code),
        "opportunity_cost": _text(row["opportunity_cost"], code),
        "hypothesis_ids": hypothesis_ids,
        "cluster_ids": cluster_ids,
        "zone_ids": zone_ids,
        "risk_tranche_id": risk_tranche_id,
        "parent_tranche_id": parent_tranche_id,
        "close_first_candidate_id": close_first,
        "reentry_obligation_id": reentry_id,
        "new_evidence_refs": new_evidence,
    }


def _take_profit_targets(
    values: Any, *, direction: str, entry: Decimal
) -> list[dict[str, Any]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
        raise V32DynamicActionPlanError("V32_ACTION_TAKE_PROFIT_INVALID")
    result: list[dict[str, Any]] = []
    for row in values:
        if not isinstance(row, Mapping) or set(row) != _TAKE_PROFIT_FIELDS:
            raise V32DynamicActionPlanError("V32_ACTION_TAKE_PROFIT_INVALID")
        action = _text(row["management_action"], "V32_ACTION_TAKE_PROFIT_INVALID")
        if action not in TAKE_PROFIT_ACTIONS:
            raise V32DynamicActionPlanError("V32_ACTION_TAKE_PROFIT_INVALID")
        price = _decimal(row["reference_price"], "V32_ACTION_TAKE_PROFIT_INVALID")
        fraction = _decimal(row["reference_fraction"], "V32_ACTION_TAKE_PROFIT_INVALID")
        if price <= 0 or (direction == "LONG" and price <= entry) or (
            direction == "SHORT" and price >= entry
        ):
            raise V32DynamicActionPlanError("V32_ACTION_TAKE_PROFIT_GEOMETRY_INVALID")
        preserves_runner = row["preserves_runner"]
        if preserves_runner is not True:
            raise V32DynamicActionPlanError("V32_ACTION_RUNNER_PRESERVATION_REQUIRED")
        if action == "PARTIAL_HARVEST":
            if not 0 < fraction < 1:
                raise V32DynamicActionPlanError("V32_ACTION_PARTIAL_FRACTION_INVALID")
        elif fraction != 0:
            raise V32DynamicActionPlanError("V32_ACTION_NON_HARVEST_FRACTION_INVALID")
        result.append(
            {
                "target_id": _text(row["target_id"], "V32_ACTION_TAKE_PROFIT_INVALID"),
                "management_action": action,
                "reference_price": canonical_decimal(price),
                "trigger_condition": _text(
                    row["trigger_condition"], "V32_ACTION_TAKE_PROFIT_INVALID"
                ),
                "reference_fraction": canonical_decimal(fraction),
                "preserves_runner": True,
            }
        )
    ids = [row["target_id"] for row in result]
    if len(ids) != len(set(ids)):
        raise V32DynamicActionPlanError("V32_ACTION_TAKE_PROFIT_ID_DUPLICATE")
    actions = {row["management_action"] for row in result}
    if "PARTIAL_HARVEST" not in actions or "RUNNER_REASSESS" not in actions:
        raise V32DynamicActionPlanError("V32_ACTION_PARTIAL_AND_RUNNER_REQUIRED")
    fraction_total = sum(
        Decimal(row["reference_fraction"])
        for row in result
        if row["management_action"] == "PARTIAL_HARVEST"
    )
    if fraction_total >= 1:
        raise V32DynamicActionPlanError("V32_ACTION_FULL_FIXED_TAKE_PROFIT_FORBIDDEN")
    return sorted(result, key=lambda row: row["target_id"])


def _trailing_plan(row: Any) -> dict[str, Any]:
    if not isinstance(row, Mapping) or set(row) != _TRAILING_FIELDS:
        raise V32DynamicActionPlanError("V32_ACTION_TRAILING_PLAN_INVALID")
    mode = _text(row["mode"], "V32_ACTION_TRAILING_PLAN_INVALID")
    if mode not in TRAILING_MODES:
        raise V32DynamicActionPlanError("V32_ACTION_TRAILING_MODE_INVALID")
    if (
        row["moves_only_to_reduce_stress"] is not True
        or row["locked_net_required_before_risk_release"] is not True
        or row["floating_gain_is_market_money"] is not False
    ):
        raise V32DynamicActionPlanError("V32_ACTION_TRAILING_SAFETY_INVALID")
    return {
        "mode": mode,
        "activation_conditions": _strings(
            row["activation_conditions"], "V32_ACTION_TRAILING_PLAN_INVALID"
        ),
        "update_rule": _text(
            row["update_rule"], "V32_ACTION_TRAILING_PLAN_INVALID"
        ),
        "basis_refs": _strings(
            row["basis_refs"], "V32_ACTION_TRAILING_PLAN_INVALID"
        ),
        "moves_only_to_reduce_stress": True,
        "locked_net_required_before_risk_release": True,
        "floating_gain_is_market_money": False,
    }


def _reentry_obligation(
    row: Any,
    *,
    as_of: datetime,
    hypotheses: Mapping[str, Mapping[str, Any]],
    clusters: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    code = "V32_ACTION_REENTRY_OBLIGATION_INVALID"
    if not isinstance(row, Mapping) or set(row) != _REENTRY_FIELDS:
        raise V32DynamicActionPlanError(code)
    direction = _text(row["direction"], code)
    state = _text(row["plan_state"], code)
    if direction not in {"LONG", "SHORT"} or state not in PLAN_STATES:
        raise V32DynamicActionPlanError(code)
    hypothesis_ids = _strings(row["parent_hypothesis_ids"], code)
    cluster_ids = _strings(row["supporting_cluster_ids"], code)
    if any(item not in hypotheses for item in hypothesis_ids) or any(
        item not in clusters or clusters[item]["direction"] != direction
        for item in cluster_ids
    ):
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_SUPPORT_INVALID")
    if any(
        not set(clusters[item]["member_hypothesis_ids"]).issubset(hypothesis_ids)
        for item in cluster_ids
    ):
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_SUPPORT_INVALID")
    max_wait = _time(row["max_wait_until"], code)
    earliest_parent_expiry = min(
        _moment(hypotheses[item]["expires_at"], code) for item in hypothesis_ids
    )
    if not as_of < _moment(max_wait, code) <= earliest_parent_expiry:
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_TIME_INVALID")
    if row["requires_new_risk_budget"] is not True or row["rewrites_prior_exit"] is not False:
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_HISTORY_OR_BUDGET_INVALID")
    return {
        "obligation_id": _text(row["obligation_id"], code),
        "source_tranche_id": _text(row["source_tranche_id"], code),
        "direction": direction,
        "plan_state": state,
        "parent_hypothesis_ids": hypothesis_ids,
        "supporting_cluster_ids": cluster_ids,
        "observation_conditions": _strings(row["observation_conditions"], code),
        "hard_falsifiers": _strings(row["hard_falsifiers"], code),
        "max_wait_until": max_wait,
        "requires_new_risk_budget": True,
        "rewrites_prior_exit": False,
    }


def _reentry_budget_state(
    row: Any,
    *,
    run_id: str,
    instrument: str,
    as_of: datetime,
    clusters: Mapping[str, Mapping[str, Any]],
    market_regime_state: Mapping[str, Any],
    current_pit_evidence_refs: frozenset[str],
) -> dict[str, Any]:
    """Normalize the run/instrument-wide churn breaker.

    Cluster and regime fields explain one failure path; they do not narrow the
    scope of this sole durable ledger or create another retry allowance.
    """

    code = "V32_ACTION_REENTRY_BUDGET_INVALID"
    if not isinstance(row, Mapping) or set(row) != _REENTRY_BUDGET_FIELDS:
        raise V32DynamicActionPlanError(code)
    budget_id = _text(row["budget_id"], code)
    churn_scope = _text(row["churn_scope"], code)
    bound_instrument = _text(row["instrument"], code)
    window_policy = _text(row["window_policy"], code)
    if (
        churn_scope != CURRENT_PILOT_REENTRY_CHURN_SCOPE
        or bound_instrument != instrument
        or window_policy != CURRENT_PILOT_REENTRY_WINDOW_POLICY
        or budget_id
        != _instrument_churn_budget_id(run_id=run_id, instrument=instrument)
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_REENTRY_INSTRUMENT_CHURN_SCOPE_INVALID"
        )
    status = _text(row["status"], code)
    direction = _text(row["direction"], code)
    if status not in REENTRY_BUDGET_STATUSES or direction not in ACTION_DIRECTIONS:
        raise V32DynamicActionPlanError(code)
    if row["obligation_forces_entry"] is not False:
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_CANNOT_FORCE_ENTRY")
    max_attempts = row["max_attempts"]
    attempts = row["attempts_used"]
    consecutive = row["consecutive_failures"]
    if (
        isinstance(max_attempts, bool)
        or max_attempts != REENTRY_MAX_ATTEMPTS
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or not 0 <= attempts <= REENTRY_MAX_ATTEMPTS
        or isinstance(consecutive, bool)
        or not isinstance(consecutive, int)
        or not 0 <= consecutive <= REENTRY_MAX_CONSECUTIVE_FAILURES
        or consecutive > attempts + 1
    ):
        raise V32DynamicActionPlanError(code)
    cumulative = _decimal(row["cumulative_reference_risk"], code)
    maximum = _decimal(row["max_cumulative_reference_risk"], code)
    failure_cluster_id = _nullable_id(row["failure_cluster_id"], code)
    start = _nullable_time(row["rolling_window_started_at"], code)
    end = _nullable_time(row["rolling_window_expires_at"], code)
    cooldown = _nullable_time(row["cooldown_until"], code)
    failure_refs = _strings(row["failure_evidence_refs"], code, allow_empty=True)
    reset_cluster_id = _nullable_id(row["reset_independent_cluster_id"], code)
    reset_previous_regime = _nullable_id(row["reset_previous_regime"], code)
    reset_current_regime = _nullable_id(row["reset_current_regime"], code)
    reset_tranche_id = _nullable_id(row["reset_new_tranche_id"], code)
    reset_refs = _strings(row["reset_evidence_refs"], code, allow_empty=True)
    reset_values = (
        reset_cluster_id,
        reset_previous_regime,
        reset_current_regime,
        reset_tranche_id,
    )
    if any(value is None for value in reset_values) != all(
        value is None for value in reset_values
    ):
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_PARTIAL_RESET_INVALID")
    has_reset = all(value is not None for value in reset_values)
    if has_reset != bool(reset_refs) or (status == "RESET") != has_reset:
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_RESET_BINDING_INVALID")

    if status == "INACTIVE":
        if (
            failure_cluster_id is not None
            or direction != "NONE"
            or start is not None
            or end is not None
            or attempts != 0
            or cumulative != 0
            or maximum != 0
            or consecutive != 0
            or cooldown is not None
            or failure_refs
            or has_reset
        ):
            raise V32DynamicActionPlanError(code)
    elif status == "INITIAL_PROBE_USED":
        start_moment = _moment(start, code) if start is not None else None
        end_moment = _moment(end, code) if end is not None else None
        budget_exhausted_without_failure = (
            attempts >= REENTRY_MAX_ATTEMPTS or cumulative >= maximum
        )
        if (
            failure_cluster_id is not None
            or direction not in {"LONG", "SHORT"}
            or start_moment is None
            or end_moment is None
            or start_moment > as_of
            or end_moment <= as_of
            or end_moment - start_moment
            != timedelta(seconds=CURRENT_PILOT_REENTRY_WINDOW_SECONDS)
            or maximum != REENTRY_MAX_CUMULATIVE_REFERENCE_RISK
            or consecutive != 0
            or cumulative > maximum
            or cumulative > CURRENT_PILOT_REFERENCE_RISK_ENVELOPE * attempts
            or cumulative < REFERENCE_RISK_QUANTUM * attempts
            or (attempts == 0 and cumulative != 0)
            or (cumulative / REFERENCE_RISK_QUANTUM)
            != (cumulative / REFERENCE_RISK_QUANTUM).to_integral_value()
            or (
                budget_exhausted_without_failure
                and (
                    cooldown is None
                    or _moment(cooldown, code) != end_moment
                )
            )
            or (not budget_exhausted_without_failure and cooldown is not None)
            or failure_refs
            or has_reset
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_INITIAL_PROBE_LOCK_INVALID"
            )
    else:
        start_moment = _moment(start, code) if start is not None else None
        end_moment = _moment(end, code) if end is not None else None
        if (
            failure_cluster_id not in clusters
            or direction not in {"LONG", "SHORT"}
            or clusters[failure_cluster_id]["direction"] != direction
            or start is None
            or end is None
            or start_moment is None
            or end_moment is None
            or start_moment > as_of
            or end_moment - start_moment
            != timedelta(seconds=CURRENT_PILOT_REENTRY_WINDOW_SECONDS)
            or maximum != REENTRY_MAX_CUMULATIVE_REFERENCE_RISK
            or cumulative > maximum
            or cumulative
            > CURRENT_PILOT_REFERENCE_RISK_ENVELOPE * attempts
            or cumulative < REFERENCE_RISK_QUANTUM * attempts
            or (cumulative / REFERENCE_RISK_QUANTUM)
            != (cumulative / REFERENCE_RISK_QUANTUM).to_integral_value()
            or (maximum / REFERENCE_RISK_QUANTUM)
            != (maximum / REFERENCE_RISK_QUANTUM).to_integral_value()
            or not failure_refs
        ):
            raise V32DynamicActionPlanError(code)
        budget_exhausted = (
            attempts >= REENTRY_MAX_ATTEMPTS
            or consecutive >= REENTRY_MAX_CONSECUTIVE_FAILURES
            or cumulative >= maximum
        )
        window_active = end_moment > as_of
        exhausted = budget_exhausted or not window_active
        active_cooldown = cooldown is not None and _moment(cooldown, code) > as_of
        if status == "RESET":
            # This row describes the new absolute window.  Whether the prior
            # window has expired is a cross-cycle fact and is checked by the
            # continuity composition before this reset can be accepted.
            assert reset_cluster_id is not None
            assert reset_previous_regime is not None
            assert reset_current_regime is not None
            if (
                attempts != 0
                or consecutive != 0
                or cumulative != 0
                or active_cooldown
                or not window_active
                or reset_cluster_id not in clusters
                or reset_cluster_id == failure_cluster_id
                or clusters[reset_cluster_id]["direction"] != direction
                or set(clusters[reset_cluster_id]["shared_dependency_groups"])
                .intersection(clusters[failure_cluster_id]["shared_dependency_groups"])
                or reset_previous_regime == reset_current_regime
                or reset_previous_regime != market_regime_state["previous_regime"]
                or reset_current_regime != market_regime_state["regime"]
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_RESET_QUALIFICATION_INVALID"
                )
        else:
            if status == "AVAILABLE" and (
                exhausted or active_cooldown or not window_active
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_AVAILABLE_INVALID"
                )
            if status == "COOLDOWN" and (
                not active_cooldown
                or exhausted
                or attempts < 1
                or consecutive < 1
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_BLOCK_STATE_INVALID"
                )
            if status == "EXHAUSTED" and not exhausted:
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_BLOCK_STATE_INVALID"
                )
            if exhausted and status != "EXHAUSTED":
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_BLOCK_STATE_INVALID"
                )
            if budget_exhausted and (
                cooldown is None or _moment(cooldown, code) != end_moment
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_EXHAUSTION_COOLDOWN_ENDPOINT_INVALID"
                )
    if not set(failure_refs + reset_refs).issubset(current_pit_evidence_refs):
        raise V32DynamicActionPlanError(
            "V32_ACTION_REENTRY_EVIDENCE_NOT_IN_CURRENT_STATE_PIT_CHAIN"
        )
    return {
        "budget_id": budget_id,
        "churn_scope": CURRENT_PILOT_REENTRY_CHURN_SCOPE,
        "instrument": instrument,
        "window_policy": CURRENT_PILOT_REENTRY_WINDOW_POLICY,
        "failure_cluster_id": failure_cluster_id,
        "direction": direction,
        "rolling_window_started_at": start,
        "rolling_window_expires_at": end,
        "attempts_used": attempts,
        "max_attempts": REENTRY_MAX_ATTEMPTS,
        "cumulative_reference_risk": canonical_decimal(cumulative),
        "max_cumulative_reference_risk": canonical_decimal(maximum),
        "consecutive_failures": consecutive,
        "cooldown_until": cooldown,
        "failure_evidence_refs": failure_refs,
        "reset_independent_cluster_id": reset_cluster_id,
        "reset_previous_regime": reset_previous_regime,
        "reset_current_regime": reset_current_regime,
        "reset_new_tranche_id": reset_tranche_id,
        "reset_evidence_refs": reset_refs,
        "status": status,
        "obligation_forces_entry": False,
    }


def _risk_tranche(
    row: Any,
    *,
    candidate: Mapping[str, Any],
    expected_risk: Decimal,
    cluster_allocations: Mapping[str, Mapping[str, Any]],
    as_of: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    code = "V32_ACTION_RISK_TRANCHE_INVALID"
    if not isinstance(row, Mapping) or set(row) not in {
        _TRANCHE_INPUT_FIELDS,
        _TRANCHE_DOCUMENT_FIELDS,
    }:
        raise V32DynamicActionPlanError(code)
    supplied_computed = set(row) == _TRANCHE_DOCUMENT_FIELDS
    entry_mode = _text(row["entry_mode"], code)
    action = candidate["action_kind"]
    allowed_modes = {
        "OPEN_PROBE": {
            "ANTICIPATORY_PROBE",
            "REACTION_ENTRY",
            "BREAK_ACCELERATION",
        },
        "ADD": {"REACTION_ENTRY", "BREAK_ACCELERATION", "RETEST_OR_REENTRY"},
        "REENTER": {"RETEST_OR_REENTRY"},
        "REVERSE": {"REACTION_ENTRY", "BREAK_ACCELERATION"},
    }[action]
    if entry_mode not in allowed_modes:
        raise V32DynamicActionPlanError("V32_ACTION_ENTRY_MODE_INVALID")
    direction = candidate["direction"]
    entry = _decimal(row["conditional_entry_reference"], code)
    stop = _decimal(row["protective_stop_reference"], code)
    previous_stop = _nullable_decimal(row["previous_stop_reference"], code)
    parent_entry = _nullable_decimal(row["parent_entry_reference"], code)
    minimum_buffer = _decimal(row["minimum_noise_execution_buffer"], code)
    multiplier = _decimal(row["multiplier_reference"], code)
    if entry <= 0 or stop <= 0 or minimum_buffer <= 0 or multiplier <= 0:
        raise V32DynamicActionPlanError(code)
    distance = entry - stop if direction == "LONG" else stop - entry
    if distance <= 0 or distance < minimum_buffer:
        raise V32DynamicActionPlanError("V32_ACTION_STOP_GEOMETRY_INVALID")
    if previous_stop is not None:
        if previous_stop <= 0 or (direction == "LONG" and stop < previous_stop) or (
            direction == "SHORT" and stop > previous_stop
        ):
            raise V32DynamicActionPlanError("V32_ACTION_STOP_RISK_EXPANSION_FORBIDDEN")
    if action == "ADD":
        if parent_entry is None or previous_stop is None or (
            direction == "LONG" and entry < parent_entry
        ) or (direction == "SHORT" and entry > parent_entry):
            raise V32DynamicActionPlanError("V32_ACTION_AVERAGING_DOWN_FORBIDDEN")
    elif parent_entry is not None or previous_stop is not None:
        raise V32DynamicActionPlanError("V32_ACTION_PARENT_OR_PREVIOUS_STOP_FORBIDDEN")

    fee = _decimal(row["fee_stress_reference"], code)
    slippage = _decimal(row["slippage_stress_reference"], code)
    funding = _decimal(row["funding_bound_reference"], code)
    gap = _decimal(row["tail_gap_reference"], code)
    if slippage <= 0 or gap <= 0:
        raise V32DynamicActionPlanError(
            "V32_ACTION_EXECUTION_STRESS_BUFFER_REQUIRED"
        )
    unit_loss = multiplier * distance + fee + slippage + funding + gap
    if unit_loss <= 0:
        raise V32DynamicActionPlanError("V32_ACTION_UNIT_LOSS_INVALID")
    scale_quantum = _decimal(row["reference_scale_quantum"], code)
    if scale_quantum <= 0:
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_SCALE_QUANTUM_INVALID")
    derived_scale = (
        (expected_risk / unit_loss / scale_quantum).to_integral_value(
            rounding=ROUND_FLOOR
        )
        * scale_quantum
    )
    if derived_scale <= 0:
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_SCALE_ZERO")

    supporting_clusters = _strings(row["supporting_cluster_ids"], code)
    if supporting_clusters != candidate["cluster_ids"] or any(
        cluster_id not in cluster_allocations for cluster_id in supporting_clusters
    ):
        raise V32DynamicActionPlanError("V32_ACTION_TRANCHE_CLUSTER_BINDING_INVALID")
    new_evidence = _strings(row["new_evidence_refs"], code, allow_empty=True)
    if new_evidence != candidate["new_evidence_refs"]:
        raise V32DynamicActionPlanError("V32_ACTION_TRANCHE_NEW_EVIDENCE_MISMATCH")
    shared = _strings(row["shared_falsifiers"], code)
    independent = _strings(row["independent_falsifiers"], code)
    if set(shared) & set(independent):
        raise V32DynamicActionPlanError("V32_ACTION_FALSIFIER_INDEPENDENCE_INVALID")
    time_stop = _time(row["time_stop_at"], code)
    time_stop_moment = _moment(time_stop, code)
    candidate_horizon = _moment(
        candidate["horizon_at"], "V32_ACTION_CANDIDATE_HORIZON_INVALID"
    )
    if not as_of < time_stop_moment <= min(expires_at, candidate_horizon):
        raise V32DynamicActionPlanError("V32_ACTION_TIME_STOP_INVALID")

    expected_unit_loss = canonical_decimal(unit_loss)
    expected_risk_text = canonical_decimal(expected_risk)
    expected_scale = canonical_decimal(derived_scale)
    if supplied_computed and (
        row["unit_loss_reference"] != expected_unit_loss
        or row["reference_risk_budget"] != expected_risk_text
        or row["derived_reference_scale"] != expected_scale
    ):
        raise V32DynamicActionPlanError("V32_ACTION_TRANCHE_COMPUTATION_MISMATCH")

    return {
        "tranche_id": _text(row["tranche_id"], code),
        "candidate_id": _text(row["candidate_id"], code),
        "entry_mode": entry_mode,
        "conditional_entry_reference": canonical_decimal(entry),
        "protective_stop_reference": canonical_decimal(stop),
        "previous_stop_reference": (
            None if previous_stop is None else canonical_decimal(previous_stop)
        ),
        "parent_entry_reference": (
            None if parent_entry is None else canonical_decimal(parent_entry)
        ),
        "minimum_noise_execution_buffer": canonical_decimal(minimum_buffer),
        "multiplier_reference": canonical_decimal(multiplier),
        "fee_stress_reference": canonical_decimal(fee),
        "slippage_stress_reference": canonical_decimal(slippage),
        "funding_bound_reference": canonical_decimal(funding),
        "tail_gap_reference": canonical_decimal(gap),
        "reference_scale_quantum": canonical_decimal(scale_quantum),
        "supporting_cluster_ids": supporting_clusters,
        "shared_falsifiers": shared,
        "independent_falsifiers": independent,
        "take_profit_targets": _take_profit_targets(
            row["take_profit_targets"], direction=direction, entry=entry
        ),
        "trailing_plan": _trailing_plan(row["trailing_plan"]),
        "time_stop_at": time_stop,
        "event_risk_guards": _strings(row["event_risk_guards"], code),
        "reentry_obligation_id": _text(row["reentry_obligation_id"], code),
        "new_evidence_refs": new_evidence,
        "reference_risk_budget": expected_risk_text,
        "unit_loss_reference": expected_unit_loss,
        "derived_reference_scale": expected_scale,
    }


def _wait_assessment(
    row: Any,
    *,
    as_of: datetime,
    expires_at: datetime,
    selected_is_wait: bool,
    eligible_risk_candidate_ids: set[str],
) -> dict[str, Any]:
    code = "V32_ACTION_WAIT_ASSESSMENT_INVALID"
    if not isinstance(row, Mapping) or set(row) != _WAIT_FIELDS:
        raise V32DynamicActionPlanError(code)
    review = _time(row["review_deadline"], code)
    if not as_of < _moment(review, code) <= expires_at:
        raise V32DynamicActionPlanError("V32_ACTION_WAIT_REVIEW_DEADLINE_INVALID")
    comparisons_raw = row["dominance_comparisons"]
    if isinstance(comparisons_raw, (str, bytes)) or not isinstance(
        comparisons_raw, Sequence
    ):
        raise V32DynamicActionPlanError(code)
    comparisons: list[dict[str, Any]] = []
    for comparison in comparisons_raw:
        if not isinstance(comparison, Mapping) or set(comparison) != _WAIT_COMPARISON_FIELDS:
            raise V32DynamicActionPlanError(code)
        reason = _text(comparison["dominance_reason"], code)
        if reason not in WAIT_DOMINANCE_REASONS:
            raise V32DynamicActionPlanError("V32_ACTION_WAIT_GENERIC_REASON_FORBIDDEN")
        comparisons.append(
            {
                "candidate_id": _text(comparison["candidate_id"], code),
                "dominance_reason": reason,
                "evidence_refs": _strings(comparison["evidence_refs"], code),
                "rationale": _text(comparison["rationale"], code),
            }
        )
    ids = [comparison["candidate_id"] for comparison in comparisons]
    if len(ids) != len(set(ids)):
        raise V32DynamicActionPlanError("V32_ACTION_WAIT_COMPARISON_DUPLICATE")
    if selected_is_wait:
        if set(ids) != eligible_risk_candidate_ids:
            raise V32DynamicActionPlanError("V32_ACTION_WAIT_DOMINANCE_COVERAGE_INVALID")
    elif comparisons:
        raise V32DynamicActionPlanError("V32_ACTION_WAIT_COMPARISON_WITHOUT_WAIT")
    return {
        "delay_cost": _text(row["delay_cost"], code),
        "missed_move_risk": _text(row["missed_move_risk"], code),
        "information_value": _text(row["information_value"], code),
        "next_observation": _text(row["next_observation"], code),
        "review_deadline": review,
        "dominance_comparisons": sorted(
            comparisons, key=lambda comparison: comparison["candidate_id"]
        ),
    }


def build_v32_dynamic_action_plan_v1(
    *,
    dynamic_research_state: Mapping[str, Any],
    plan_id: str,
    expires_at: str,
    reference_context: str,
    reference_tranche_state: Mapping[str, Any],
    plan_state: str,
    reference_risk_unit_budget: Decimal | str,
    candidates: Sequence[Mapping[str, Any]],
    risk_tranches: Sequence[Mapping[str, Any]],
    reentry_obligations: Sequence[Mapping[str, Any]],
    reentry_budget_state: Mapping[str, Any],
    selected_candidate_id: str,
    alternative_candidate_rank: Sequence[str],
    wait_assessment: Mapping[str, Any],
    inactivity_opportunity_watchdog: Mapping[str, Any],
    future_execution_hazard: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one complete, local, non-executable V3.2 planning bundle."""

    if (
        isinstance(candidates, (str, bytes))
        or not isinstance(candidates, Sequence)
        or len(candidates) > MAX_ACTION_CANDIDATES
    ):
        raise V32DynamicActionPlanError("V32_ACTION_CANDIDATE_LIMIT_EXCEEDED")

    try:
        dynamic_digest = verify_v32_dynamic_research_state_v1(dynamic_research_state)
    except Exception as exc:
        raise V32DynamicActionPlanError("V32_ACTION_DYNAMIC_STATE_INVALID") from exc
    run_id = _text(dynamic_research_state["run_id"], "V32_ACTION_RUN_ID_INVALID")
    cycle_index = dynamic_research_state["cycle_index"]
    as_of_text = _time(dynamic_research_state["as_of"], "V32_ACTION_AS_OF_INVALID")
    as_of = _moment(as_of_text, "V32_ACTION_AS_OF_INVALID")
    expires_text = _time(expires_at, "V32_ACTION_EXPIRES_AT_INVALID")
    expires = _moment(expires_text, "V32_ACTION_EXPIRES_AT_INVALID")
    if expires <= as_of:
        raise V32DynamicActionPlanError("V32_ACTION_EXPIRES_AT_INVALID")
    if reference_context not in REFERENCE_CONTEXTS or plan_state != "CONDITIONAL":
        raise V32DynamicActionPlanError("V32_ACTION_PLAN_STATE_INVALID")
    normalized_reference_tranche = _reference_tranche_state(
        reference_tranche_state,
        reference_context=reference_context,
        as_of=as_of,
    )

    hypotheses = {
        row["hypothesis_id"]: row for row in dynamic_research_state["hypotheses"]
    }
    clusters = {
        row["cluster_id"]: row
        for row in dynamic_research_state["dependency_clusters"]
    }
    zones = {row["zone_id"]: row for row in dynamic_research_state["zones"]}
    if normalized_reference_tranche["status"] == "ACTIVE" and (
        any(
            hypothesis_id not in hypotheses
            for hypothesis_id in normalized_reference_tranche[
                "supporting_hypothesis_ids"
            ]
        )
        or any(
            hypotheses[hypothesis_id]["direction"]
            != normalized_reference_tranche["direction"]
            or hypotheses[hypothesis_id]["status"]
            not in ACTIONABLE_HYPOTHESIS_STATUSES
            or _moment(
                hypotheses[hypothesis_id]["expires_at"],
                "V32_ACTION_REFERENCE_TRANCHE_SUPPORT_BINDING_INVALID",
            )
            <= as_of
            for hypothesis_id in normalized_reference_tranche[
                "supporting_hypothesis_ids"
            ]
            if hypothesis_id in hypotheses
        )
        or any(
            cluster_id not in clusters
            or clusters[cluster_id]["direction"]
            != normalized_reference_tranche["direction"]
            for cluster_id in normalized_reference_tranche[
                "supporting_cluster_ids"
            ]
        )
        or any(
            not set(clusters[cluster_id]["member_hypothesis_ids"]).issubset(
                normalized_reference_tranche["supporting_hypothesis_ids"]
            )
            for cluster_id in normalized_reference_tranche[
                "supporting_cluster_ids"
            ]
            if cluster_id in clusters
        )
        or {
            hypothesis_id
            for cluster_id in normalized_reference_tranche[
                "supporting_cluster_ids"
            ]
            if cluster_id in clusters
            for hypothesis_id in clusters[cluster_id]["member_hypothesis_ids"]
            if hypothesis_id in hypotheses
            and hypotheses[hypothesis_id]["status"]
            in ACTIONABLE_HYPOTHESIS_STATUSES
        }
        != set(normalized_reference_tranche["supporting_hypothesis_ids"])
        or any(
            zone_id not in zones
            for zone_id in normalized_reference_tranche["zone_ids"]
        )
        or any(
            _moment(
                zones[zone_id]["expires_at"],
                "V32_ACTION_REFERENCE_TRANCHE_SUPPORT_BINDING_INVALID",
            )
            <= as_of
            for zone_id in normalized_reference_tranche["zone_ids"]
            if zone_id in zones
        )
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_REFERENCE_TRANCHE_SUPPORT_BINDING_INVALID"
        )
    instruments = {str(row["instrument"]) for row in zones.values()}
    if len(instruments) != 1:
        raise V32DynamicActionPlanError(
            "V32_ACTION_SINGLE_INSTRUMENT_SCOPE_REQUIRED"
        )
    instrument = next(iter(instruments))
    unknowns = {row["unknown_id"]: row for row in dynamic_research_state["unknowns"]}
    modifiers = {
        row["modifier_id"]: row for row in dynamic_research_state["path_modifiers"]
    }
    current_pit_refs = _current_state_pit_evidence_refs(dynamic_research_state)
    normalized_reentry_budget = _reentry_budget_state(
        reentry_budget_state,
        run_id=run_id,
        instrument=instrument,
        as_of=as_of,
        clusters=clusters,
        market_regime_state=dynamic_research_state["market_regime_state"],
        current_pit_evidence_refs=current_pit_refs,
    )

    normalized_candidates = [
        _candidate(
            row,
            as_of=as_of,
            expires_at=expires,
            hypotheses=hypotheses,
            clusters=clusters,
            zones=zones,
            unknowns=unknowns,
            modifiers=modifiers,
        )
        for row in candidates
    ]
    candidate_ids = [row["candidate_id"] for row in normalized_candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise V32DynamicActionPlanError("V32_ACTION_CANDIDATE_ID_DUPLICATE")
    candidate_map = {row["candidate_id"]: row for row in normalized_candidates}
    parent_candidates = [
        row
        for row in normalized_candidates
        if row["action_kind"] in {"ADD", "HOLD", "REDUCE", "CLOSE", "REVERSE"}
    ]
    if normalized_reference_tranche["status"] == "ACTIVE":
        if not parent_candidates or any(
            candidate["parent_tranche_id"]
            != normalized_reference_tranche["tranche_id"]
            for candidate in parent_candidates
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_REFERENCE_TRANCHE_CANDIDATE_BINDING_INVALID"
            )
        if any(
            candidate["action_kind"] in {"ADD", "REVERSE"}
            and candidate["risk_tranche_id"]
            == normalized_reference_tranche["tranche_id"]
            for candidate in normalized_candidates
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_NEW_TRANCHE_ID_MUST_DIFFER_FROM_PARENT"
            )
    elif parent_candidates:
        raise V32DynamicActionPlanError(
            "V32_ACTION_REFERENCE_TRANCHE_CANDIDATE_BINDING_INVALID"
        )
    expected_keys = legal_v32_dynamic_action_keys_v1(reference_context)
    actual_keys = [(row["action_kind"], row["direction"]) for row in normalized_candidates]
    expected_wait_count = 1 if ("WAIT", "NONE") in expected_keys else 0
    if (
        set(actual_keys) != set(expected_keys)
        or actual_keys.count(("WAIT", "NONE")) != expected_wait_count
    ):
        raise V32DynamicActionPlanError("V32_ACTION_LEGAL_GRID_INCOMPLETE")

    regime = dynamic_research_state["market_regime_state"]
    regime_is_nondirectional = (
        regime["regime"] in CURRENT_DIRECTIONAL_ZERO_RISK_MARKET_REGIMES
    )
    regime_refs = set(
        regime["evidence_refs"]
        + regime["counter_evidence_refs"]
        + regime["transition_evidence_refs"]
    )
    if regime_is_nondirectional:
        for candidate in normalized_candidates:
            if candidate["action_kind"] not in RISK_INCREASING_ACTIONS:
                continue
            if (
                candidate["plan_state"] != "CONDITIONAL"
                or candidate["feasibility"] != "BLOCKED"
                or candidate["risk_tranche_id"] is not None
                or candidate["block_reason"]
                not in {
                    "MARKET_REGIME_NON_DIRECTIONAL",
                    "FACT_INTEGRITY",
                    "MAX_LOSS",
                    "PATH_MODIFIER_INVALIDATION",
                    "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
                }
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_NONDIRECTIONAL_REGIME_MUST_BLOCK_NEW_RISK"
                )
            if not candidate["zone_ids"] or any(
                zones[zone_id]["role"] != "BREAKOUT_BOUNDARY"
                for zone_id in candidate["zone_ids"]
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_NONDIRECTIONAL_BREAKOUT_BOUNDARY_REQUIRED"
                )
            if (
                candidate["block_reason"] == "MARKET_REGIME_NON_DIRECTIONAL"
                and candidate["blocking_evidence_refs"] != sorted(regime_refs)
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_NONDIRECTIONAL_REGIME_EVIDENCE_REQUIRED"
                )
    research_breakout_trigger_pairs = _derive_research_breakout_trigger_pairs(
        run_id=run_id,
        cycle_index=cycle_index,
        as_of=as_of_text,
        regime_is_nondirectional=regime_is_nondirectional,
        candidates=normalized_candidates,
        zones=zones,
    )

    churn_budget_closed = normalized_reentry_budget["status"] in {
        "COOLDOWN",
        "EXHAUSTED",
    } or (
        normalized_reentry_budget["status"] == "INITIAL_PROBE_USED"
        and (
            normalized_reentry_budget["attempts_used"]
            >= normalized_reentry_budget["max_attempts"]
            or Decimal(
                normalized_reentry_budget["cumulative_reference_risk"]
            )
            >= Decimal(
                normalized_reentry_budget[
                    "max_cumulative_reference_risk"
                ]
            )
        )
    )
    churn_budget_blocking_refs = (
        normalized_reentry_budget["failure_evidence_refs"]
        or [INSTRUMENT_CHURN_BUDGET_LIMIT_REACHED_REF]
    )
    prior_churn_gate_reasons = {
        "FACT_INTEGRITY",
        "MARKET_REGIME_NON_DIRECTIONAL",
        "PATH_MODIFIER_INVALIDATION",
        "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
    }
    for candidate in normalized_candidates:
        if candidate["action_kind"] not in INSTRUMENT_CHURN_ACTION_KINDS:
            continue
        if churn_budget_closed:
            valid_prior_gate = (
                candidate["feasibility"] == "BLOCKED"
                and candidate["block_reason"] in prior_churn_gate_reasons
            )
            valid_budget_gate = (
                candidate["feasibility"] == "BLOCKED"
                and candidate["plan_state"] == "CONDITIONAL"
                and candidate["block_reason"]
                == "REENTRY_COOLDOWN_OR_BUDGET"
                and candidate["blocking_evidence_refs"]
                == churn_budget_blocking_refs
                and candidate["risk_tranche_id"] is None
            )
            if not valid_prior_gate and not valid_budget_gate:
                raise V32DynamicActionPlanError(
                    "V32_ACTION_INSTRUMENT_CHURN_BUDGET_MUST_BLOCK"
                )
        elif candidate["block_reason"] == "REENTRY_COOLDOWN_OR_BUDGET":
            raise V32DynamicActionPlanError(
                "V32_ACTION_REENTRY_BUDGET_BLOCK_WITHOUT_CAUSE"
            )

    selected = _text(selected_candidate_id, "V32_ACTION_SELECTED_CANDIDATE_INVALID")
    if selected not in candidate_map or candidate_map[selected]["feasibility"] != "ELIGIBLE":
        raise V32DynamicActionPlanError("V32_ACTION_SELECTED_CANDIDATE_INVALID")
    alternatives = _ordered_strings(
        alternative_candidate_rank,
        "V32_ACTION_ALTERNATIVE_RANK_INVALID",
        allow_empty=len(candidate_ids) == 1,
    )
    if set(alternatives) != set(candidate_ids) - {selected}:
        raise V32DynamicActionPlanError("V32_ACTION_ALTERNATIVE_RANK_INCOMPLETE")

    for candidate in normalized_candidates:
        if candidate["action_kind"] == "REVERSE":
            close_id = candidate["close_first_candidate_id"]
            close_candidate = candidate_map.get(close_id)
            if (
                close_candidate is None
                or close_candidate["action_kind"] != "CLOSE"
                or close_candidate["feasibility"] != "ELIGIBLE"
                or close_candidate["parent_tranche_id"]
                != candidate["parent_tranche_id"]
            ):
                raise V32DynamicActionPlanError("V32_ACTION_REVERSE_CLOSE_FIRST_INVALID")

    normalized_obligations = [
        _reentry_obligation(
            row, as_of=as_of, hypotheses=hypotheses, clusters=clusters
        )
        for row in reentry_obligations
    ]
    obligation_ids = [row["obligation_id"] for row in normalized_obligations]
    if len(obligation_ids) != len(set(obligation_ids)):
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_ID_DUPLICATE")
    obligation_map = {row["obligation_id"]: row for row in normalized_obligations}
    consumed_obligation_ids: set[str] = set()
    for candidate in normalized_candidates:
        if candidate["action_kind"] == "REENTER":
            obligation = obligation_map.get(candidate["reentry_obligation_id"])
            if (
                obligation is None
                or obligation["direction"] != candidate["direction"]
                or obligation["plan_state"] != "CONDITIONAL"
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REENTRY_OBLIGATION_NOT_ELIGIBLE"
                )
            consumed_obligation_ids.add(candidate["reentry_obligation_id"])
            if not regime_is_nondirectional:
                budget_available = normalized_reentry_budget["status"] in {
                    "AVAILABLE",
                    "RESET",
                }
                if not budget_available:
                    allowed_prior_gate = candidate["block_reason"] in {
                        "FACT_INTEGRITY",
                        "PATH_MODIFIER_INVALIDATION",
                        "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
                    }
                    valid_budget_block = (
                        candidate["feasibility"] == "BLOCKED"
                        and candidate["plan_state"] == "CONDITIONAL"
                        and candidate["block_reason"]
                        == "REENTRY_COOLDOWN_OR_BUDGET"
                        and normalized_reentry_budget["status"]
                        in {"COOLDOWN", "EXHAUSTED"}
                        and bool(
                            normalized_reentry_budget[
                                "failure_evidence_refs"
                            ]
                        )
                        and candidate["blocking_evidence_refs"]
                        == normalized_reentry_budget[
                            "failure_evidence_refs"
                        ]
                    )
                    if not allowed_prior_gate and not valid_budget_block:
                        raise V32DynamicActionPlanError(
                            "V32_ACTION_REENTRY_BUDGET_MUST_BLOCK"
                        )
                elif (
                    candidate["block_reason"]
                    == "REENTRY_COOLDOWN_OR_BUDGET"
                ):
                    raise V32DynamicActionPlanError(
                        "V32_ACTION_REENTRY_BUDGET_BLOCK_WITHOUT_CAUSE"
                    )
                elif candidate["feasibility"] == "ELIGIBLE":
                    expected_cluster = (
                        normalized_reentry_budget["reset_independent_cluster_id"]
                        if normalized_reentry_budget["status"] == "RESET"
                        else normalized_reentry_budget["failure_cluster_id"]
                    )
                    if (
                        candidate["direction"]
                        != normalized_reentry_budget["direction"]
                        or expected_cluster not in candidate["cluster_ids"]
                        or (
                            normalized_reentry_budget["status"] == "RESET"
                            and candidate["risk_tranche_id"]
                            != normalized_reentry_budget["reset_new_tranche_id"]
                        )
                    ):
                        raise V32DynamicActionPlanError(
                            "V32_ACTION_REENTRY_BUDGET_BINDING_INVALID"
                        )

    modifier_assessments = [
        _candidate_path_modifier_assessment(
            candidate,
            hypotheses=hypotheses,
            zones=zones,
            modifiers=modifiers,
        )
        for candidate in normalized_candidates
    ]
    modifier_assessment_map = {
        row["candidate_id"]: row for row in modifier_assessments
    }
    reference_budget = _decimal(
        reference_risk_unit_budget, "V32_ACTION_REFERENCE_RISK_BUDGET_INVALID"
    )
    if reference_budget != CURRENT_PILOT_REFERENCE_RISK_ENVELOPE:
        raise V32DynamicActionPlanError("V32_ACTION_REFERENCE_RISK_ENVELOPE_INVALID")
    for _ in range(MAX_ACTION_CANDIDATES + 1):
        eligible_risk_candidates = [
            candidate
            for candidate in normalized_candidates
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS
            and candidate["feasibility"] == "ELIGIBLE"
        ]
        eligible_cluster_ids = [
            cluster_id
            for candidate in eligible_risk_candidates
            for cluster_id in candidate["cluster_ids"]
        ]
        if len(eligible_cluster_ids) != len(set(eligible_cluster_ids)):
            raise V32DynamicActionPlanError("V32_ACTION_CLUSTER_RISK_DOUBLE_COUNTED")
        (
            normalized_availability,
            subjective_tier_cap_units,
            directional_subjective_tier_cap_units,
            residual_uncertainty_tier,
            residual_uncertainty_cap_units,
            risk_bottleneck_cap_units,
            distributable_budget,
        ) = _risk_availability(
            raw_budget=reference_budget,
            eligible_risk_candidates=eligible_risk_candidates,
            eligible_cluster_ids=eligible_cluster_ids,
            clusters=clusters,
            hypotheses=hypotheses,
            market_regime_state=regime,
            current_pit_evidence_refs=current_pit_refs,
        )
        pre_modifier_allocations = _allocate_cluster_risk(
            reference_risk_budget=distributable_budget,
            raw_reference_risk_budget=reference_budget,
            directional_subjective_tier_cap_units=(
                directional_subjective_tier_cap_units
            ),
            cluster_ids=eligible_cluster_ids,
            clusters=clusters,
        )
        allocations, post_modifier_budget = _apply_path_modifier_risk_caps(
            allocations=pre_modifier_allocations,
            eligible_risk_candidates=eligible_risk_candidates,
            assessments=modifier_assessment_map,
        )
        provisional = {
            row["cluster_id"]: Decimal(row["reference_risk"])
            for row in allocations
        }
        zero_candidate_ids = {
            candidate["candidate_id"]
            for candidate in eligible_risk_candidates
            if sum(
                (provisional[cluster_id] for cluster_id in candidate["cluster_ids"]),
                Decimal("0"),
            )
            <= 0
        }
        if not zero_candidate_ids:
            break
        for candidate in normalized_candidates:
            if candidate["candidate_id"] not in zero_candidate_ids:
                continue
            candidate["plan_state"] = "CONDITIONAL"
            candidate["feasibility"] = "BLOCKED"
            candidate["block_reason"] = "RISK_BUDGET_BELOW_CLUSTER_QUANTUM"
            candidate["blocking_unknown_ids"] = []
            candidate["blocking_evidence_refs"] = sorted(
                {
                    ref
                    for hypothesis_id in candidate["hypothesis_ids"]
                    for ref in hypotheses[hypothesis_id]["source_refs"]
                }
            )
            candidate["risk_tranche_id"] = None
    else:
        raise V32DynamicActionPlanError(
            "V32_ACTION_RISK_QUANTUM_SELECTION_DID_NOT_CONVERGE"
        )

    # ``RISK_BUDGET_BELOW_CLUSTER_QUANTUM`` is produced by this builder, not
    # selected by the Agent.  On reconstruction it arrives as an already
    # blocked candidate, so bind it back to the only currently reachable
    # owning cause: residual uncertainty has reduced the global envelope to
    # zero.  Exact source refs prevent arbitrary evidence from being attached
    # to an otherwise valid zero-risk decision.
    for candidate in normalized_candidates:
        if candidate["block_reason"] != "RISK_BUDGET_BELOW_CLUSTER_QUANTUM":
            continue
        expected_refs = sorted(
            {
                ref
                for hypothesis_id in candidate["hypothesis_ids"]
                for ref in hypotheses[hypothesis_id]["source_refs"]
            }
        )
        if (
            candidate["action_kind"] not in RISK_INCREASING_ACTIONS
            or residual_uncertainty_cap_units != 0
            or candidate["feasibility"] != "BLOCKED"
            or candidate["plan_state"] != "CONDITIONAL"
            or candidate["blocking_unknown_ids"]
            or candidate["blocking_evidence_refs"] != expected_refs
            or candidate["risk_tranche_id"] is not None
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_RISK_QUANTUM_BLOCK_WITHOUT_CAUSE"
            )

    # Feasibility is an owning-system decision, not an Agent narrative knob.
    # Every blocked candidate must therefore have a cause reconstructed above
    # or a single pending Application proof.  Geometry and generic planning
    # prose remain useful diagnostics/guards, but cannot silently delete one
    # legal alternative until a typed owner exists for them.
    owned_risk_block_reasons = {
        "FACT_INTEGRITY",
        "MARKET_REGIME_NON_DIRECTIONAL",
        "NO_NEW_EVIDENCE",
        "PATH_MODIFIER_INVALIDATION",
        "REENTRY_COOLDOWN_OR_BUDGET",
        "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
        "SUBJECTIVE_TIER_EXTREME_UNCERTAINTY",
    }
    for candidate in normalized_candidates:
        if candidate["feasibility"] != "BLOCKED":
            continue
        if candidate["action_kind"] not in RISK_INCREASING_ACTIONS:
            raise V32DynamicActionPlanError(
                "V32_ACTION_UNOWNED_FEASIBILITY_BLOCK_FORBIDDEN"
            )
        reason = candidate["block_reason"]
        if reason == "COST_OR_LIQUIDITY":
            if candidate["blocking_evidence_refs"] != [
                OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE_REF
            ]:
                raise V32DynamicActionPlanError(
                    "V32_ACTION_UNOWNED_FEASIBILITY_BLOCK_FORBIDDEN"
                )
            continue
        if (
            reason not in owned_risk_block_reasons
            or (
                reason == "MARKET_REGIME_NON_DIRECTIONAL"
                and not regime_is_nondirectional
            )
            or (
                reason == "NO_NEW_EVIDENCE"
                and (
                    candidate["action_kind"]
                    not in {"ADD", "REENTER", "REVERSE"}
                    or candidate["blocking_evidence_refs"]
                    != [NO_NEW_CURRENT_PIT_EVIDENCE_REF]
                    or candidate["new_evidence_refs"]
                    or candidate["blocking_unknown_ids"]
                )
            )
            or (
                reason == "REENTRY_COOLDOWN_OR_BUDGET"
                and (
                    candidate["action_kind"]
                    not in INSTRUMENT_CHURN_ACTION_KINDS
                    or not churn_budget_closed
                    or candidate["blocking_evidence_refs"]
                    != churn_budget_blocking_refs
                )
            )
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_UNOWNED_FEASIBILITY_BLOCK_FORBIDDEN"
            )
    if candidate_map[selected]["feasibility"] != "ELIGIBLE":
        raise V32DynamicActionPlanError("V32_ACTION_SELECTED_CANDIDATE_INVALID")
    allocation_map = {row["cluster_id"]: row for row in allocations}
    normalized_hazard = _future_execution_hazard(future_execution_hazard)
    execution_gate = _current_execution_gate(normalized_hazard)

    tranche_rows = list(risk_tranches)
    tranche_ids_from_input: list[str] = []
    candidate_ids_from_input: list[str] = []
    for row in tranche_rows:
        if not isinstance(row, Mapping):
            raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_INVALID")
        tranche_ids_from_input.append(_text(row.get("tranche_id"), "V32_ACTION_RISK_TRANCHE_INVALID"))
        candidate_ids_from_input.append(_text(row.get("candidate_id"), "V32_ACTION_RISK_TRANCHE_INVALID"))
    if len(tranche_ids_from_input) != len(set(tranche_ids_from_input)) or len(
        candidate_ids_from_input
    ) != len(set(candidate_ids_from_input)):
        raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_ID_DUPLICATE")
    expected_tranche_ids = {
        candidate["risk_tranche_id"] for candidate in eligible_risk_candidates
    }
    if set(tranche_ids_from_input) != expected_tranche_ids or set(
        candidate_ids_from_input
    ) != {candidate["candidate_id"] for candidate in eligible_risk_candidates}:
        raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_COVERAGE_INVALID")

    normalized_tranches: list[dict[str, Any]] = []
    for row in tranche_rows:
        candidate = candidate_map[row["candidate_id"]]
        if row["tranche_id"] != candidate["risk_tranche_id"]:
            raise V32DynamicActionPlanError("V32_ACTION_RISK_TRANCHE_BINDING_INVALID")
        expected_risk = sum(
            Decimal(allocation_map[cluster_id]["reference_risk"])
            for cluster_id in candidate["cluster_ids"]
        )
        normalized_tranches.append(
            _risk_tranche(
                row,
                candidate=candidate,
                expected_risk=expected_risk,
                cluster_allocations=allocation_map,
                as_of=as_of,
                expires_at=expires,
            )
        )
    tranche_map = {row["tranche_id"]: row for row in normalized_tranches}
    if normalized_reference_tranche["status"] == "ACTIVE":
        for candidate in normalized_candidates:
            if candidate["action_kind"] != "ADD" or candidate["feasibility"] != "ELIGIBLE":
                continue
            tranche = tranche_map.get(candidate["risk_tranche_id"])
            if (
                tranche is None
                or tranche["parent_entry_reference"]
                != normalized_reference_tranche["entry_reference"]
                or tranche["previous_stop_reference"]
                != normalized_reference_tranche["protective_stop_reference"]
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_REFERENCE_TRANCHE_GEOMETRY_BINDING_INVALID"
                )
    if normalized_reentry_budget["status"] == "RESET" and (
        normalized_reentry_budget["reset_new_tranche_id"] not in tranche_map
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_REENTRY_RESET_NEW_TRANCHE_REQUIRED"
        )
    for tranche in normalized_tranches:
        if normalized_hazard["hazard_id"] not in tranche["event_risk_guards"]:
            raise V32DynamicActionPlanError(
                "V32_ACTION_EXECUTION_HAZARD_NOT_BOUND_TO_TRANCHE"
            )
        obligation = obligation_map.get(tranche["reentry_obligation_id"])
        candidate = candidate_map[tranche["candidate_id"]]
        if (
            obligation is None
            or obligation["source_tranche_id"] != tranche["tranche_id"]
            or obligation["direction"] != candidate["direction"]
        ):
            raise V32DynamicActionPlanError(
                "V32_ACTION_TRANCHE_REENTRY_OBLIGATION_INVALID"
            )
    for obligation in normalized_obligations:
        if obligation["source_tranche_id"] in tranche_map:
            tranche = tranche_map[obligation["source_tranche_id"]]
            if (
                tranche["reentry_obligation_id"] != obligation["obligation_id"]
                or obligation["plan_state"] != "PLANNED"
            ):
                raise V32DynamicActionPlanError(
                    "V32_ACTION_TRANCHE_REENTRY_OBLIGATION_INVALID"
                )
    future_obligation_ids = {
        tranche["reentry_obligation_id"] for tranche in normalized_tranches
    }
    if set(obligation_map) != consumed_obligation_ids | future_obligation_ids:
        raise V32DynamicActionPlanError("V32_ACTION_REENTRY_OBLIGATION_UNBOUND")

    wait = _wait_assessment(
        wait_assessment,
        as_of=as_of,
        expires_at=expires,
        selected_is_wait=candidate_map[selected]["action_kind"] == "WAIT",
        eligible_risk_candidate_ids={
            candidate["candidate_id"] for candidate in eligible_risk_candidates
        },
    )
    watchdog = _inactivity_watchdog(
        inactivity_opportunity_watchdog,
        as_of=as_of,
        expires_at=expires,
        candidate_ids=set(candidate_ids),
        risk_candidate_ids={
            candidate["candidate_id"]
            for candidate in normalized_candidates
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS
        },
    )
    selected_reference_risk = (
        sum(
            (
                Decimal(allocation_map[cluster_id]["reference_risk"])
                for cluster_id in candidate_map[selected]["cluster_ids"]
            ),
            Decimal("0"),
        )
        if candidate_map[selected]["action_kind"] in RISK_INCREASING_ACTIONS
        else Decimal("0")
    )
    selected_candidate = candidate_map[selected]
    if (
        normalized_reentry_budget["status"] == "INACTIVE"
        and selected_reference_risk > 0
        and selected_candidate["action_kind"] in {"REENTER", "REVERSE"}
    ):
        raise V32DynamicActionPlanError(
            "V32_ACTION_INACTIVE_LEDGER_RISK_ALIAS_FORBIDDEN"
        )
    selected_consumes_instrument_churn = (
        selected_reference_risk > 0
        and v32_action_consumes_instrument_churn_budget_v1(
            action_kind=selected_candidate["action_kind"],
            reentry_budget_status=normalized_reentry_budget["status"],
        )
    )
    if selected_consumes_instrument_churn:
        cumulative = Decimal(
            normalized_reentry_budget["cumulative_reference_risk"]
        )
        maximum = Decimal(
            normalized_reentry_budget["max_cumulative_reference_risk"]
        )
        remaining = maximum - cumulative
        if (
            normalized_reentry_budget["status"]
            not in {"INITIAL_PROBE_USED", "AVAILABLE", "RESET"}
            or normalized_reentry_budget["attempts_used"]
            >= normalized_reentry_budget["max_attempts"]
            or remaining <= 0
            or selected_reference_risk > remaining
        ):
            error_code = (
                "V32_ACTION_REENTRY_SELECTED_BUDGET_EXCEEDED"
                if selected_candidate["action_kind"] == "REENTER"
                else "V32_ACTION_INSTRUMENT_CHURN_SELECTED_BUDGET_EXCEEDED"
            )
            raise V32DynamicActionPlanError(
                error_code
            )

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "cycle_index": cycle_index,
        "plan_id": _text(plan_id, "V32_ACTION_PLAN_ID_INVALID"),
        "as_of": as_of_text,
        "expires_at": expires_text,
        "dynamic_research_state_digest": dynamic_digest,
        "reference_context": reference_context,
        "reference_tranche_state": normalized_reference_tranche,
        "plan_state": plan_state,
        "reference_risk_unit_budget": canonical_decimal(reference_budget),
        "subjective_tier_cap_units": subjective_tier_cap_units,
        "directional_subjective_tier_cap_units": (
            directional_subjective_tier_cap_units
        ),
        "residual_uncertainty_tier": residual_uncertainty_tier,
        "residual_uncertainty_cap_units": residual_uncertainty_cap_units,
        "risk_bottleneck_cap_units": risk_bottleneck_cap_units,
        "path_modifier_candidate_assessments": sorted(
            modifier_assessments, key=lambda row: row["candidate_id"]
        ),
        "pre_modifier_reference_risk_budget": canonical_decimal(
            distributable_budget
        ),
        "risk_availability_assessment": normalized_availability,
        "distributable_reference_risk_budget": canonical_decimal(
            post_modifier_budget
        ),
        "selected_candidate_reference_risk_budget": canonical_decimal(
            selected_reference_risk
        ),
        "current_executable_reference_risk_budget": "0",
        "legal_actions_considered": [
            {"action_kind": action, "direction": direction}
            for action, direction in expected_keys
        ],
        "candidates": sorted(
            normalized_candidates, key=lambda candidate: candidate["candidate_id"]
        ),
        "research_breakout_trigger_pairs": research_breakout_trigger_pairs,
        "cluster_risk_allocations": allocations,
        "risk_tranches": sorted(
            normalized_tranches, key=lambda tranche: tranche["tranche_id"]
        ),
        "reentry_obligations": sorted(
            normalized_obligations, key=lambda obligation: obligation["obligation_id"]
        ),
        "reentry_budget_state": normalized_reentry_budget,
        "selected_candidate_id": selected,
        "alternative_candidate_rank": alternatives,
        "wait_assessment": wait,
        "inactivity_opportunity_watchdog": watchdog,
        "future_execution_hazard": normalized_hazard,
        "execution_gate": execution_gate,
        "risk_allocation_policy": (
            "THREE_TIER_SUBJECTIVE_CAP_ONLY_NO_SUM_MAX_TIER_PER_DIRECTION_"
            "MIN_TIER_AND_RESIDUAL_ONLY_AFTER_TYPED_HARD_GATES_NO_"
            "COVERAGE_REGIME_LIQUIDITY_OR_GEOMETRY_SCALAR_"
            "THEN_DISCRETE_LOW_ONE_HIGH_TWO_RELATIVE_UNITS_0_000001_"
            "THEN_PATH_MODIFIER_NON_INFLATION_CAP"
        ),
        "resource_limits": {"action_candidates": MAX_ACTION_CANDIDATES},
        "resource_policy": "TOTAL_CANDIDATE_HARD_CAP_FAIL_CLOSED_NO_TRUNCATION",
        "planning_scope": "PUBLIC_DATA_LOCAL_NON_EXECUTABLE_REFERENCE_RISK_ONLY",
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "execution_claim": "NONE_RESEARCH_PLAN_ONLY",
        "account_claim": "NONE_NO_ACCOUNT_STATE",
        "fill_claim": "NONE_NO_FILL_MODEL",
        "pnl_claim": "NONE_NO_PNL_MODEL",
        "market_money_claim": "FORBIDDEN_FLOATING_GAIN_REMAINS_AT_RISK",
        "probability_claim": "NONE_UNCALIBRATED_SUBJECTIVE_SUPPORT_ONLY",
        "expected_value_allowed": False,
        "executable": False,
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_dynamic_action_plan_v1(
    document: Mapping[str, Any], *, dynamic_research_state: Mapping[str, Any]
) -> str:
    """Reconstruct and verify one V3.2 action plan against its research state."""

    if not isinstance(document, Mapping) or set(document) != _STATE_FIELDS:
        raise V32DynamicActionPlanError("V32_ACTION_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
    except Exception as exc:
        raise V32DynamicActionPlanError("V32_ACTION_DIGEST_INVALID") from exc
    rebuilt = build_v32_dynamic_action_plan_v1(
        dynamic_research_state=dynamic_research_state,
        plan_id=document["plan_id"],
        expires_at=document["expires_at"],
        reference_context=document["reference_context"],
        reference_tranche_state=document["reference_tranche_state"],
        plan_state=document["plan_state"],
        reference_risk_unit_budget=document["reference_risk_unit_budget"],
        candidates=document["candidates"],
        risk_tranches=document["risk_tranches"],
        reentry_obligations=document["reentry_obligations"],
        reentry_budget_state=document["reentry_budget_state"],
        selected_candidate_id=document["selected_candidate_id"],
        alternative_candidate_rank=document["alternative_candidate_rank"],
        wait_assessment=document["wait_assessment"],
        inactivity_opportunity_watchdog=document[
            "inactivity_opportunity_watchdog"
        ],
        future_execution_hazard=document["future_execution_hazard"],
    )
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32DynamicActionPlanError("V32_ACTION_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "ACTION_DIRECTIONS",
    "ACTION_KINDS",
    "BLOCK_REASONS",
    "DIGEST_FIELD",
    "ENTRY_MODES",
    "FEASIBILITY_STATES",
    "INSTRUMENT_CHURN_ACTION_KINDS",
    "INSTRUMENT_CHURN_BUDGET_LIMIT_REACHED_REF",
    "PLAN_STATES",
    "REFERENCE_CONTEXTS",
    "REFERENCE_RISK_QUANTUM",
    "REENTRY_BUDGET_STATUSES",
    "REENTRY_MAX_ATTEMPTS",
    "REENTRY_MAX_CONSECUTIVE_FAILURES",
    "REENTRY_MAX_CUMULATIVE_REFERENCE_RISK",
    "REQUIRED_EXECUTION_HAZARD_SCENARIOS",
    "RISK_INCREASING_ACTIONS",
    "SCHEMA_ID",
    "TAKE_PROFIT_ACTIONS",
    "TRAILING_MODES",
    "FUTURE_EXECUTION_CONTROL_REQUIREMENTS",
    "MAX_ACTION_CANDIDATES",
    "NO_NEW_CURRENT_PIT_EVIDENCE_REF",
    "OBJECTIVE_REFERENCE_INPUTS_UNAVAILABLE_REF",
    "V32DynamicActionPlanError",
    "WAIT_DOMINANCE_REASONS",
    "build_v32_dynamic_action_plan_v1",
    "compute_v32_effective_reference_risk_v1",
    "legal_v32_dynamic_action_keys_v1",
    "v32_action_consumes_instrument_churn_budget_v1",
    "verify_v32_dynamic_action_plan_v1",
]
