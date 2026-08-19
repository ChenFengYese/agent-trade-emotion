from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.v32_dynamic_action_plan import (
    RISK_INCREASING_ACTIONS,
    V32DynamicActionPlanError,
    _allocate_cluster_risk,
    build_v32_dynamic_action_plan_v1,
    compute_v32_effective_reference_risk_v1,
    legal_v32_dynamic_action_keys_v1,
    verify_v32_dynamic_action_plan_v1,
)
from trade_system.theory_paper_v2.domain.v32_dynamic_research import (
    UNKNOWN_BEHAVIOR_EFFECT,
    build_v32_dynamic_research_state_v1,
)


AS_OF = "2026-08-07T00:00:00Z"
EXPIRES = "2026-08-07T01:00:00Z"
REENTRY_WINDOW_EXPIRES = "2026-08-07T23:00:00Z"
HORIZON = "2026-08-07T00:45:00Z"
INSTRUMENT = "BTC-USDT-SWAP"
REENTRY_BUDGET_ID = "instrument-churn::v32-test-run::BTC-USDT-SWAP"


def _hypothesis(
    hypothesis_id: str,
    hypothesis_type: str,
    direction: str,
    tier: str,
    *,
    opposition_ids: list[str] | None = None,
    alternative_ids: list[str] | None = None,
    dependency_group: str | None = None,
) -> dict:
    dependency_group = dependency_group or f"dependency:{hypothesis_id}"
    return {
        "hypothesis_id": hypothesis_id,
        "hypothesis_type": hypothesis_type,
        "direction": direction,
        "scope": "BTC-USDT-SWAP",
        "regime_scope": ["INTRADAY", "RANGE_TRANSITION"],
        "mechanism": f"mechanism for {hypothesis_id}",
        "horizon_seconds": 3600,
        "source_refs": [
            f"source:{hypothesis_id}",
            f"source-independent:{hypothesis_id}",
        ],
        "dependency_groups": [
            dependency_group,
            f"{dependency_group}:independent",
        ],
        "supporting_refs": [
            f"support:{hypothesis_id}",
            f"support-independent:{hypothesis_id}",
        ],
        "opposing_refs": [f"opposing:{hypothesis_id}"],
        "opposition_ids": opposition_ids or [],
        "alternative_ids": alternative_ids or [],
        "hard_falsifiers": [f"falsifier:{hypothesis_id}"],
        "soft_contradictions": [f"soft:{hypothesis_id}"],
        "path_modifier_ids": [],
        "next_observation": f"observe {hypothesis_id}",
        "expires_at": EXPIRES,
        "previous_expires_at": None,
        "renewal_evidence_refs": [],
        "parent_revision_digest": None,
        "status": "ACTIVE",
        "subjective_plausibility_tier": tier,
        "previous_subjective_plausibility_tier": None,
        "tier_update_refs": [],
        "lineage_id": hypothesis_id,
        "lineage_revision": 1,
        "predecessor_id": None,
        "predecessor_fingerprint": None,
        "semantic_fingerprint": None,
    }


def _dynamic_state(
    *,
    long_tier: str = "HIGH",
    short_tier: str = "LOW",
    other_tier: str = "EXTREME_UNCERTAINTY",
    unknown_tier: str = "EXTREME_UNCERTAINTY",
) -> dict:
    hypotheses = [
        _hypothesis(
            "h-long",
            "STATE",
            "LONG",
            long_tier,
            opposition_ids=["h-short"],
            alternative_ids=["h-short", "h-unknown"],
            dependency_group="dependency:state",
        ),
        _hypothesis(
            "h-short",
            "STATE",
            "SHORT",
            short_tier,
            opposition_ids=["h-long"],
            alternative_ids=["h-long", "h-unknown"],
            dependency_group="dependency:state",
        ),
        _hypothesis(
            "h-neutral",
            "ATTRIBUTION",
            "NEUTRAL",
            "LOW",
            alternative_ids=["h-unknown"],
            dependency_group="dependency:attribution",
        ),
        _hypothesis(
            "h-zone-short",
            "FORECAST_PATH",
            "SHORT",
            "LOW",
            opposition_ids=["h-zone-long"],
            alternative_ids=["h-zone-long", "h-false-break", "h-other"],
            dependency_group="dependency:zone",
        ),
        _hypothesis(
            "h-zone-long",
            "FORECAST_PATH",
            "LONG",
            "LOW",
            opposition_ids=["h-zone-short", "h-false-break"],
            alternative_ids=["h-zone-short", "h-false-break", "h-other"],
            dependency_group="dependency:zone",
        ),
        _hypothesis(
            "h-false-break",
            "FORECAST_PATH",
            "SHORT",
            "LOW",
            opposition_ids=["h-zone-long"],
            alternative_ids=["h-zone-short", "h-zone-long", "h-other"],
            dependency_group="dependency:zone",
        ),
        _hypothesis(
            "h-other",
            "FORECAST_PATH",
            "OTHER",
            other_tier,
            alternative_ids=["h-zone-short", "h-zone-long", "h-false-break"],
            dependency_group="dependency:zone-other",
        ),
        _hypothesis(
            "h-action-long",
            "ACTION_THESIS",
            "LONG",
            "LOW",
            opposition_ids=["h-action-short"],
            alternative_ids=["h-action-short", "h-unknown"],
            dependency_group="dependency:action",
        ),
        _hypothesis(
            "h-action-short",
            "ACTION_THESIS",
            "SHORT",
            "LOW",
            opposition_ids=["h-action-long"],
            alternative_ids=["h-action-long", "h-unknown"],
            dependency_group="dependency:action",
        ),
        _hypothesis(
            "h-unknown",
            "ATTRIBUTION",
            "UNKNOWN",
            unknown_tier,
            alternative_ids=["h-neutral"],
            dependency_group="dependency:unknown",
        ),
    ]
    clusters = [
        {
            "cluster_id": "c-long",
            "member_hypothesis_ids": ["h-long"],
            "direction": "LONG",
            "shared_dependency_groups": ["dependency:state"],
            "aggregate_tier": long_tier,
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-short",
            "member_hypothesis_ids": ["h-short"],
            "direction": "SHORT",
            "shared_dependency_groups": ["dependency:state"],
            "aggregate_tier": short_tier,
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-neutral",
            "member_hypothesis_ids": ["h-neutral"],
            "direction": "NEUTRAL",
            "shared_dependency_groups": ["dependency:attribution"],
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-zone-short",
            "member_hypothesis_ids": ["h-zone-short", "h-false-break"],
            "direction": "SHORT",
            "shared_dependency_groups": ["dependency:zone"],
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-zone-long",
            "member_hypothesis_ids": ["h-zone-long"],
            "direction": "LONG",
            "shared_dependency_groups": ["dependency:zone"],
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-action-long",
            "member_hypothesis_ids": ["h-action-long"],
            "direction": "LONG",
            "shared_dependency_groups": ["dependency:action"],
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
        {
            "cluster_id": "c-action-short",
            "member_hypothesis_ids": ["h-action-short"],
            "direction": "SHORT",
            "shared_dependency_groups": ["dependency:action"],
            "aggregate_tier": "LOW",
            "aggregation_method": "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
        },
    ]
    unknowns = [
        {
            "unknown_id": unknown_id,
            "unknown_type": unknown_type,
            "scope": f"scope for {unknown_id}",
            "dependency_refs": [f"dependency:{unknown_id}"],
            "behavior_effect": UNKNOWN_BEHAVIOR_EFFECT[unknown_type],
            "explanation": f"explanation for {unknown_id}",
        }
        for unknown_id, unknown_type in (
            ("u-cause", "UNKNOWN_CAUSE"),
            ("u-fact", "UNKNOWN_FACT_INTEGRITY"),
            ("u-loss", "UNKNOWN_MAX_LOSS"),
        )
    ]
    return build_v32_dynamic_research_state_v1(
        run_id="v32-test-run",
        cycle_index=1,
        as_of=AS_OF,
        frame_mode="FULL_CONTEXT",
        previous_state_digest=None,
        market_regime_state={
            "regime": "TREND_UP",
            "evidence_refs": ["source:h-long"],
            "counter_evidence_refs": ["opposing:h-long"],
            "regime_feature_assessments": [],
            "expires_at": EXPIRES,
            "previous_regime": None,
            "transition_evidence_refs": [],
        },
        unknowns=unknowns,
        zones=[
            {
                "zone_id": "z-main",
                "instrument": "BTC-USDT-SWAP",
                "role": "BREAKOUT_BOUNDARY",
                "lower_bound": "99",
                "upper_bound": "101",
                "construction_method": "MULTI_SOURCE_COMPOSITE",
                "created_at": "2026-08-06T23:00:00Z",
                "available_at": "2026-08-06T23:59:00Z",
                "expires_at": EXPIRES,
                "evidence_refs": ["zone-evidence"],
                "dependency_groups": ["dependency:state", "dependency:zone"],
                "touch_count": 3,
                "touch_refs": ["touch-1", "touch-2", "touch-3"],
                "reaction_refs": ["reaction-1"],
                "volume_at_price_refs": ["volume-profile"],
                "dwell_time_refs": ["dwell-ledger"],
                "round_number_refs": ["round-number-100"],
                "orderbook_flow_refs": ["flow-snapshot"],
                "leverage_refs": ["oi-datum"],
                "options_refs": [],
                "quality": "HIGH",
                "alternative_zone_ids": [],
                "path_modifier_ids": [],
                "path_hypothesis_ids": {
                    "ZONE_REJECTION": "h-zone-short",
                    "ZONE_ABSORPTION_BREAK": "h-zone-long",
                    "FALSE_BREAK_REVERSION": "h-false-break",
                    "ZONE_NO_EFFECT_OTHER": "h-other",
                },
                "lineage_id": "z-main",
                "lineage_revision": 1,
                "predecessor_id": None,
                "predecessor_fingerprint": None,
                "semantic_fingerprint": None,
            }
        ],
        hypotheses=hypotheses,
        path_modifiers=[],
        dependency_clusters=clusters,
    )


def _dynamic_state_with_modifier(
    *,
    effect: str,
    status: str = "ACTIVE",
    modifier_id: str = "modifier-state-long",
    dynamic_state: dict | None = None,
    target_hypothesis_id: str = "h-long",
) -> dict:
    state = dynamic_state or _dynamic_state()
    hypotheses = deepcopy(state["hypotheses"])
    next(
        row
        for row in hypotheses
        if row["hypothesis_id"] == target_hypothesis_id
    )[
        "path_modifier_ids"
    ] = [modifier_id]
    return build_v32_dynamic_research_state_v1(
        run_id=state["run_id"],
        cycle_index=state["cycle_index"],
        as_of=state["as_of"],
        frame_mode=state["frame_mode"],
        previous_state_digest=state["previous_state_digest"],
        market_regime_state=state["market_regime_state"],
        unknowns=state["unknowns"],
        zones=state["zones"],
        hypotheses=hypotheses,
        path_modifiers=[
            {
                "modifier_id": modifier_id,
                "modifier_type": "FALSE_BREAK_STOP_RUN",
                "scope": "BTC-USDT-SWAP",
                "effect": effect,
                "mechanism": "a stop run can change the long path without becoming a vote",
                "source_refs": [f"source:{modifier_id}"],
                "dependency_groups": ["dependency:state"],
                "affected_hypothesis_ids": [target_hypothesis_id],
                "affected_zone_ids": [],
                "affected_action_kinds": [
                    "OPEN_PROBE",
                    "ADD",
                    "REENTER",
                    "REVERSE",
                ],
                "conditions": ["stop-run condition is observed"],
                "trigger_effect": "REQUIRE_RECLAIM_CONFIRMATION",
                "protection_effect": "REQUIRE_EXIT_REENTRY_SEPARATION",
                "invalidators": ["sustained acceptance invalidates stop-run path"],
                "created_at": "2026-08-06T23:30:00Z",
                "available_at": "2026-08-06T23:59:00Z",
                "expires_at": EXPIRES,
                "status": status,
                "lineage_id": modifier_id,
                "lineage_revision": 1,
                "predecessor_id": None,
                "predecessor_fingerprint": None,
                "semantic_fingerprint": None,
            }
        ],
        dependency_clusters=state["dependency_clusters"],
    )


def _dynamic_state_with_regime(
    regime: str, *, zone_role: str = "BREAKOUT_BOUNDARY"
) -> dict:
    state = _dynamic_state()
    feature_assessments: list[dict[str, object]] = []
    regime_evidence_refs = ["source:h-long"]
    if regime == "CHOPPY":
        feature_assessments = [
            {
                "feature_type": "DIRECTIONAL_PERSISTENCE",
                "feature_state": "LOW",
                "evidence_refs": ["regime:price-persistence"],
            },
            {
                "feature_type": "REVERSAL_FREQUENCY",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:price-reversals"],
            },
            {
                "feature_type": "EXECUTION_CHURN_PRESSURE",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:trade-churn"],
            },
        ]
    elif regime == "VOLATILITY_WITHOUT_DIRECTION":
        feature_assessments = [
            {
                "feature_type": "DIRECTIONAL_PERSISTENCE",
                "feature_state": "LOW",
                "evidence_refs": ["regime:price-persistence"],
            },
            {
                "feature_type": "REALIZED_VOLATILITY",
                "feature_state": "HIGH",
                "evidence_refs": ["regime:price-volatility"],
            },
            {
                "feature_type": "DIRECTIONAL_IMBALANCE",
                "feature_state": "BALANCED",
                "evidence_refs": ["regime:flow-balance"],
            },
        ]
    regime_evidence_refs.extend(
        evidence_ref
        for assessment in feature_assessments
        for evidence_ref in assessment["evidence_refs"]
    )
    return build_v32_dynamic_research_state_v1(
        run_id=state["run_id"],
        cycle_index=state["cycle_index"],
        as_of=state["as_of"],
        frame_mode=state["frame_mode"],
        previous_state_digest=state["previous_state_digest"],
        market_regime_state={
            "regime": regime,
            "evidence_refs": regime_evidence_refs,
            "counter_evidence_refs": ["opposing:h-long"],
            "regime_feature_assessments": feature_assessments,
            "expires_at": EXPIRES,
            "previous_regime": None,
            "transition_evidence_refs": [],
        },
        unknowns=state["unknowns"],
        zones=[
            {**zone, "role": zone_role, "semantic_fingerprint": None}
            for zone in state["zones"]
        ],
        hypotheses=state["hypotheses"],
        path_modifiers=state["path_modifiers"],
        dependency_clusters=state["dependency_clusters"],
    )


def _cycle_two_transition_state() -> dict:
    previous = _dynamic_state()
    hypotheses = deepcopy(previous["hypotheses"])
    for hypothesis in hypotheses:
        hypothesis["parent_revision_digest"] = previous["dynamic_research_state_digest"]
        hypothesis["previous_subjective_plausibility_tier"] = hypothesis[
            "subjective_plausibility_tier"
        ]
        hypothesis["previous_expires_at"] = hypothesis["expires_at"]
        hypothesis["tier_update_refs"] = []
        hypothesis["renewal_evidence_refs"] = []
    return build_v32_dynamic_research_state_v1(
        run_id=previous["run_id"],
        cycle_index=2,
        as_of="2026-08-07T00:15:00Z",
        frame_mode="DELTA_UPDATE",
        previous_state_digest=previous["dynamic_research_state_digest"],
        market_regime_state={
            "regime": "RANGE",
            "evidence_refs": ["source:h-long"],
            "counter_evidence_refs": ["opposing:h-long"],
            "regime_feature_assessments": [],
            "expires_at": EXPIRES,
            "previous_regime": "TREND_UP",
            "transition_evidence_refs": ["source:h-short"],
        },
        unknowns=previous["unknowns"],
        zones=previous["zones"],
        hypotheses=hypotheses,
        path_modifiers=previous["path_modifiers"],
        dependency_clusters=previous["dependency_clusters"],
    )


def _candidate(
    candidate_id: str,
    action: str,
    direction: str,
    *,
    hypothesis_ids: list[str] | None = None,
    cluster_ids: list[str] | None = None,
    risk_tranche_id: str | None = None,
    parent_tranche_id: str | None = None,
    close_first_candidate_id: str | None = None,
    reentry_obligation_id: str | None = None,
    new_evidence_refs: list[str] | None = None,
    feasibility: str = "ELIGIBLE",
    block_reason: str = "NONE",
    blocking_unknown_ids: list[str] | None = None,
    blocking_evidence_refs: list[str] | None = None,
) -> dict:
    is_wait = action == "WAIT"
    return {
        "candidate_id": candidate_id,
        "action_kind": action,
        "direction": direction,
        "plan_state": "CONDITIONAL",
        "feasibility": feasibility,
        "block_reason": block_reason,
        "blocking_unknown_ids": blocking_unknown_ids or [],
        "blocking_evidence_refs": blocking_evidence_refs or [],
        "trigger_conditions": ["absolute trigger condition"],
        "guard_conditions": ["risk and integrity guards"],
        "invalidation_conditions": ["hard invalidator"],
        "horizon_at": HORIZON,
        "next_observation": "next closed 15 minute observation",
        "opportunity_cost": "missed move or adverse selection",
        "hypothesis_ids": [] if is_wait else hypothesis_ids or [],
        "cluster_ids": [] if is_wait else cluster_ids or [],
        "zone_ids": [] if is_wait else ["z-main"],
        "risk_tranche_id": risk_tranche_id,
        "parent_tranche_id": parent_tranche_id,
        "close_first_candidate_id": close_first_candidate_id,
        "reentry_obligation_id": reentry_obligation_id,
        "new_evidence_refs": new_evidence_refs or [],
    }


def _tranche(
    tranche_id: str,
    candidate_id: str,
    direction: str,
    cluster_id: str,
    obligation_id: str,
    *,
    action: str = "OPEN_PROBE",
    entry: str = "100",
    stop: str | None = None,
    previous_stop: str | None = None,
    parent_entry: str | None = None,
    new_evidence_refs: list[str] | None = None,
) -> dict:
    stop = stop or ("95" if direction == "LONG" else "105")
    target = "106" if direction == "LONG" else "94"
    return {
        "tranche_id": tranche_id,
        "candidate_id": candidate_id,
        "entry_mode": (
            "REACTION_ENTRY"
            if action in {"ADD", "REVERSE"}
            else "RETEST_OR_REENTRY" if action == "REENTER" else "ANTICIPATORY_PROBE"
        ),
        "conditional_entry_reference": entry,
        "protective_stop_reference": stop,
        "previous_stop_reference": previous_stop,
        "parent_entry_reference": parent_entry,
        "minimum_noise_execution_buffer": "1",
        "multiplier_reference": "0.1",
        "fee_stress_reference": "0.02",
        "slippage_stress_reference": "0.03",
        "funding_bound_reference": "0.01",
        "tail_gap_reference": "0.04",
        "reference_scale_quantum": "0.000001",
        "supporting_cluster_ids": [cluster_id],
        "shared_falsifiers": ["shared thesis falsifier"],
        "independent_falsifiers": ["independent execution falsifier"],
        "take_profit_targets": [
            {
                "target_id": f"{tranche_id}-harvest",
                "management_action": "PARTIAL_HARVEST",
                "reference_price": target,
                "trigger_condition": "first structure objective touched",
                "reference_fraction": "0.5",
                "preserves_runner": True,
            },
            {
                "target_id": f"{tranche_id}-runner",
                "management_action": "RUNNER_REASSESS",
                "reference_price": target,
                "trigger_condition": "trend continuation remains valid",
                "reference_fraction": "0",
                "preserves_runner": True,
            },
        ],
        "trailing_plan": {
            "mode": "STRUCTURE_VOLATILITY_LOCKED_NET",
            "activation_conditions": ["structure milestone and noise buffer pass"],
            "update_rule": "move only toward lower stress after fresh evidence",
            "basis_refs": ["structure-ref", "volatility-ref", "cost-ref"],
            "moves_only_to_reduce_stress": True,
            "locked_net_required_before_risk_release": True,
            "floating_gain_is_market_money": False,
        },
        "time_stop_at": HORIZON,
        "event_risk_guards": ["event-calendar", "hazard-v1"],
        "reentry_obligation_id": obligation_id,
        "new_evidence_refs": new_evidence_refs or [],
    }


def _obligation(
    obligation_id: str,
    source_tranche_id: str,
    direction: str,
    hypothesis_id: str,
    cluster_id: str,
    *,
    plan_state: str = "PLANNED",
) -> dict:
    return {
        "obligation_id": obligation_id,
        "source_tranche_id": source_tranche_id,
        "direction": direction,
        "plan_state": plan_state,
        "parent_hypothesis_ids": [hypothesis_id],
        "supporting_cluster_ids": [cluster_id],
        "observation_conditions": ["retest or renewed structure response"],
        "hard_falsifiers": ["parent thesis hard falsifier"],
        "max_wait_until": EXPIRES,
        "requires_new_risk_budget": True,
        "rewrites_prior_exit": False,
    }


def _wait(comparisons: list[dict] | None = None) -> dict:
    return {
        "delay_cost": "a fast move can leave the reference zone",
        "missed_move_risk": "break acceleration may occur before confirmation",
        "information_value": "the next closed bar discriminates rejection from break",
        "next_observation": "next closed 15 minute bar and flow delta",
        "review_deadline": "2026-08-07T00:15:00Z",
        "dominance_comparisons": comparisons or [],
    }


def _risk_availability() -> dict:
    return {
        "derivation_policy": "FORBIDDEN_AGENT_INPUT",
        "hypothesis_evidence_chain_coverage": "COMPLETE",
        "hypothesis_evidence_refs": ["support:h-long"],
        "missing_hypothesis_evidence_requirements": [],
        "source_admission_coverage_status": "UNKNOWN_NOT_IN_DYNAMIC_STATE",
        "regime_gate_status": "ALLOWED_NO_EXTRA_SCALAR",
        "geometry_gate_status": "PASSED_BY_TYPED_CANDIDATE_AND_TRANCHE_VALIDATION",
    }


def _watchdog(*, due: bool = False) -> dict:
    return {
        "inactivity_since": "2026-08-06T22:00:00Z" if due else AS_OF,
        "consecutive_wait_cycles": 8 if due else 0,
        "testable_risk_plan_review_due": due,
        "model_adaptation_inactivity_since": (
            "2026-08-06T22:00:00Z" if due else AS_OF
        ),
        "consecutive_model_stale_cycles": 8 if due else 0,
        "model_adaptation_review_due": due,
        "max_wait_cycles_before_review": 8,
        "max_inactivity_seconds": 7200,
        "forced_review_due": due,
        "required_responses": (
            ["BASELINE_COMPARISON", "FULL_OPPORTUNITY_REVIEW", "SHADOW_PLAN_REFRESH"]
            if due
            else []
        ),
        "baseline_comparison_refs": ["wait-only-baseline", "simple-trend-baseline"] if due else [],
        "shadow_plan_candidate_ids": ["open-long", "open-short"] if due else [],
        "next_watchdog_review_at": "2026-08-07T00:15:00Z",
        "forces_action": False,
        "shadow_plan_scope": "CONDITIONAL_RESEARCH_COMPARISON_NO_FILL_OR_FORCED_ENTRY",
        "clock_semantics": (
            "DUAL_DURABLE_CLOCKS_TESTABLE_RISK_PLAN_AND_MODEL_ADAPTATION_"
            "NEITHER_IS_REAL_EXPOSURE"
        ),
        "real_exposure_claim": "NONE_RESEARCH_PLAN_ONLY",
    }


def _hazard() -> dict:
    return {
        "hazard_id": "hazard-v1",
        "future_latency_bound_ms": None,
        "latency_qualification_status": "UNKNOWN_NOT_QUALIFIED",
        "latency_evidence_refs": [],
        "network_failure_scenario": "future transport can time out or reject",
        "required_scenarios": [
            "CANCEL_REPLACE_RACE",
            "LIMIT_NOT_FILLED_OR_QUEUE_LOSS",
            "NETWORK_TIMEOUT_OR_PARTITION",
            "PROTECTION_ACK_UNKNOWN",
            "RATE_LIMIT_OR_REJECTION",
            "STOP_THROUGH_OR_GAP",
            "VENUE_UNAVAILABLE",
        ],
        "future_execution_control_requirements": [
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
        ],
        "unbounded_venue_outage_status": (
            "UNKNOWN_MAX_LOSS_BLOCKS_FUTURE_EXECUTION"
        ),
        "guaranteed_exit_price": False,
        "model_scope": "FUTURE_EXECUTION_HAZARD_ONLY",
        "stop_semantics": "STOP_TRIGGER_IS_NOT_FILL_GAP_SLIPPAGE_REJECTION_REMAIN",
        "current_order_claim": "NONE_NO_CURRENT_ORDER",
        "current_protection_claim": "NONE_NO_CURRENT_PROTECTION",
    }


def _inactive_reentry_budget() -> dict:
    return {
        "budget_id": REENTRY_BUDGET_ID,
        "churn_scope": "RUN_SINGLE_INSTRUMENT_WIDE",
        "instrument": INSTRUMENT,
        "window_policy": "ABSOLUTE_24H_NO_EARLY_RESET",
        "failure_cluster_id": None,
        "direction": "NONE",
        "rolling_window_started_at": None,
        "rolling_window_expires_at": None,
        "attempts_used": 0,
        "max_attempts": 2,
        "cumulative_reference_risk": "0",
        "max_cumulative_reference_risk": "0",
        "consecutive_failures": 0,
        "cooldown_until": None,
        "failure_evidence_refs": [],
        "reset_independent_cluster_id": None,
        "reset_previous_regime": None,
        "reset_current_regime": None,
        "reset_new_tranche_id": None,
        "reset_evidence_refs": [],
        "status": "INACTIVE",
        "obligation_forces_entry": False,
    }


def _available_reentry_budget() -> dict:
    return {
        "budget_id": REENTRY_BUDGET_ID,
        "churn_scope": "RUN_SINGLE_INSTRUMENT_WIDE",
        "instrument": INSTRUMENT,
        "window_policy": "ABSOLUTE_24H_NO_EARLY_RESET",
        "failure_cluster_id": "c-long",
        "direction": "LONG",
        "rolling_window_started_at": "2026-08-06T23:00:00Z",
        "rolling_window_expires_at": REENTRY_WINDOW_EXPIRES,
        "attempts_used": 1,
        "max_attempts": 2,
        "cumulative_reference_risk": "0.25",
        "max_cumulative_reference_risk": "2",
        "consecutive_failures": 1,
        "cooldown_until": AS_OF,
        "failure_evidence_refs": ["source:h-long"],
        "reset_independent_cluster_id": None,
        "reset_previous_regime": None,
        "reset_current_regime": None,
        "reset_new_tranche_id": None,
        "reset_evidence_refs": [],
        "status": "AVAILABLE",
        "obligation_forces_entry": False,
    }


def _flat_args(*, dynamic_state: dict | None = None) -> dict:
    state = dynamic_state or _dynamic_state()
    reentry_budget = _inactive_reentry_budget()
    instruments = {row["instrument"] for row in state["zones"]}
    if len(instruments) != 1:
        raise AssertionError("fixture requires one instrument")
    reentry_budget["budget_id"] = (
        f"instrument-churn::{state['run_id']}::{next(iter(instruments))}"
    )
    return {
        "dynamic_research_state": state,
        "plan_id": "plan-flat-1",
        "expires_at": EXPIRES,
        "reference_context": "FLAT_RESEARCH_INTENT",
        "reference_tranche_state": {
            "status": "NONE",
            "tranche_id": None,
            "direction": "NONE",
            "entry_reference": None,
            "protective_stop_reference": None,
            "valid_until": None,
            "supporting_hypothesis_ids": [],
            "supporting_cluster_ids": [],
            "zone_ids": [],
        },
        "plan_state": "CONDITIONAL",
        "reference_risk_unit_budget": "1",
        "candidates": [
            _candidate(
                "open-long",
                "OPEN_PROBE",
                "LONG",
                hypothesis_ids=["h-long"],
                cluster_ids=["c-long"],
                risk_tranche_id="t-long",
            ),
            _candidate(
                "open-short",
                "OPEN_PROBE",
                "SHORT",
                hypothesis_ids=["h-short"],
                cluster_ids=["c-short"],
                risk_tranche_id="t-short",
            ),
            _candidate("wait", "WAIT", "NONE"),
        ],
        "risk_tranches": [
            _tranche("t-long", "open-long", "LONG", "c-long", "o-long"),
            _tranche("t-short", "open-short", "SHORT", "c-short", "o-short"),
        ],
        "reentry_obligations": [
            _obligation("o-long", "t-long", "LONG", "h-long", "c-long"),
            _obligation("o-short", "t-short", "SHORT", "h-short", "c-short"),
        ],
        "reentry_budget_state": reentry_budget,
        "selected_candidate_id": "open-long",
        "alternative_candidate_rank": ["open-short", "wait"],
        "wait_assessment": _wait(),
        "inactivity_opportunity_watchdog": _watchdog(),
        "future_execution_hazard": _hazard(),
    }


def _long_intent_args() -> dict:
    new_long = ["fresh-confirmation-evidence"]
    new_short = ["fresh-reversal-evidence"]
    return {
        "dynamic_research_state": _dynamic_state(),
        "plan_id": "plan-long-intent-1",
        "expires_at": EXPIRES,
        "reference_context": "LONG_RESEARCH_INTENT",
        "reference_tranche_state": {
            "status": "ACTIVE",
            "tranche_id": "prior-long-tranche",
            "direction": "LONG",
            "entry_reference": "100",
            "protective_stop_reference": "95",
            "valid_until": HORIZON,
            "supporting_hypothesis_ids": ["h-long"],
            "supporting_cluster_ids": ["c-long"],
            "zone_ids": ["z-main"],
        },
        "plan_state": "CONDITIONAL",
        "reference_risk_unit_budget": "1",
        "candidates": [
            _candidate(
                "add-long",
                "ADD",
                "LONG",
                hypothesis_ids=["h-long"],
                cluster_ids=["c-long"],
                risk_tranche_id="t-add",
                parent_tranche_id="prior-long-tranche",
                new_evidence_refs=new_long,
            ),
            _candidate(
                "hold-long",
                "HOLD",
                "LONG",
                hypothesis_ids=["h-long"],
                cluster_ids=["c-long"],
                parent_tranche_id="prior-long-tranche",
            ),
            _candidate(
                "reduce-long",
                "REDUCE",
                "LONG",
                hypothesis_ids=["h-short"],
                cluster_ids=["c-short"],
                parent_tranche_id="prior-long-tranche",
            ),
            _candidate(
                "close-long",
                "CLOSE",
                "LONG",
                hypothesis_ids=["h-short"],
                cluster_ids=["c-short"],
                parent_tranche_id="prior-long-tranche",
            ),
            _candidate(
                "reverse-short",
                "REVERSE",
                "SHORT",
                hypothesis_ids=["h-short"],
                cluster_ids=["c-short"],
                risk_tranche_id="t-reverse",
                parent_tranche_id="prior-long-tranche",
                close_first_candidate_id="close-long",
                new_evidence_refs=new_short,
            ),
        ],
        "risk_tranches": [
            _tranche(
                "t-add",
                "add-long",
                "LONG",
                "c-long",
                "o-add",
                action="ADD",
                entry="101",
                stop="96",
                previous_stop="95",
                parent_entry="100",
                new_evidence_refs=new_long,
            ),
            _tranche(
                "t-reverse",
                "reverse-short",
                "SHORT",
                "c-short",
                "o-reverse",
                action="REVERSE",
                entry="99",
                stop="104",
                new_evidence_refs=new_short,
            ),
        ],
        "reentry_obligations": [
            _obligation("o-add", "t-add", "LONG", "h-long", "c-long"),
            _obligation("o-reverse", "t-reverse", "SHORT", "h-short", "c-short"),
        ],
        "reentry_budget_state": _inactive_reentry_budget(),
        "selected_candidate_id": "add-long",
        "alternative_candidate_rank": [
            "hold-long",
            "reduce-long",
            "close-long",
            "reverse-short",
        ],
        "wait_assessment": _wait(),
        "inactivity_opportunity_watchdog": _watchdog(),
        "future_execution_hazard": _hazard(),
    }


class V32DynamicActionPlanTests(unittest.TestCase):
    def test_candidate_resource_limit_fails_closed_before_any_truncation(self) -> None:
        args = _flat_args()
        args["candidates"] = [deepcopy(args["candidates"][0]) for _ in range(17)]
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_CANDIDATE_LIMIT_EXCEEDED",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_candidate_zone_must_bind_to_supporting_path_or_dependency(self) -> None:
        state = _dynamic_state()
        zones = deepcopy(state["zones"])
        zones[0]["dependency_groups"] = ["dependency:zone"]
        zones[0]["semantic_fingerprint"] = None
        unrelated = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=zones,
            hypotheses=state["hypotheses"],
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_ZONE_SUPPORT_BINDING_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**_flat_args(dynamic_state=unrelated))

    def test_zone_modifier_closure_cannot_be_omitted_by_candidate_hypothesis(self) -> None:
        state = _dynamic_state()
        hypotheses = deepcopy(state["hypotheses"])
        zones = deepcopy(state["zones"])
        zones[0]["path_modifier_ids"] = ["modifier-zone-stop-run"]
        next(
            row for row in hypotheses if row["hypothesis_id"] == "h-zone-short"
        )["path_modifier_ids"] = ["modifier-zone-stop-run"]
        modifier = {
            "modifier_id": "modifier-zone-stop-run",
            "modifier_type": "FALSE_BREAK_STOP_RUN",
            "scope": "BTC-USDT-SWAP",
            "effect": "INVALIDATES_PATH",
            "mechanism": "zone stop-run invalidates unprotected entries",
            "source_refs": ["source:zone-stop-run"],
            "dependency_groups": ["dependency:zone"],
            "affected_hypothesis_ids": ["h-zone-short"],
            "affected_zone_ids": ["z-main"],
            "affected_action_kinds": ["OPEN_PROBE", "REENTER", "ADD", "REVERSE"],
            "conditions": ["false break enters the zone"],
            "trigger_effect": "CANCEL_TRIGGER",
            "protection_effect": "BLOCK_PROTECTION_ASSUMPTION",
            "invalidators": ["sustained acceptance outside the zone"],
            "created_at": "2026-08-06T23:30:00Z",
            "available_at": "2026-08-06T23:59:00Z",
            "expires_at": EXPIRES,
            "status": "ACTIVE",
            "lineage_id": "modifier-zone-stop-run",
            "lineage_revision": 1,
            "predecessor_id": None,
            "predecessor_fingerprint": None,
            "semantic_fingerprint": None,
        }
        bounded = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=zones,
            hypotheses=hypotheses,
            path_modifiers=[modifier],
            dependency_clusters=state["dependency_clusters"],
        )
        args = _flat_args(dynamic_state=bounded)
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_DERIVED_HARD_GATE_MUST_BLOCK_NEW_RISK",
        ):
            build_v32_dynamic_action_plan_v1(**args)

        for candidate in args["candidates"]:
            if candidate["action_kind"] == "OPEN_PROBE":
                candidate.update(
                    {
                        "feasibility": "BLOCKED",
                        "block_reason": "PATH_MODIFIER_INVALIDATION",
                        "blocking_evidence_refs": ["source:zone-stop-run"],
                        "risk_tranche_id": None,
                    }
                )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        args["wait_assessment"] = _wait()
        document = build_v32_dynamic_action_plan_v1(**args)
        assessments = {
            row["candidate_id"]: row
            for row in document["path_modifier_candidate_assessments"]
        }
        for candidate_id in ("open-long", "open-short"):
            self.assertEqual(
                ["modifier-zone-stop-run"],
                assessments[candidate_id]["invalidating_modifier_ids"],
            )

    def test_low_tier_caps_total_risk_without_denominator_amplification(self) -> None:
        state = _dynamic_state_with_modifier(
            effect="INVALIDATES_PATH",
            modifier_id="modifier-short-cost-owner",
            dynamic_state=_dynamic_state(long_tier="LOW"),
            target_hypothesis_id="h-short",
        )
        args = _flat_args(dynamic_state=state)
        short = next(
            row for row in args["candidates"] if row["candidate_id"] == "open-short"
        )
        short.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "PATH_MODIFIER_INVALIDATION",
                "blocking_evidence_refs": ["source:modifier-short-cost-owner"],
                "risk_tranche_id": None,
            }
        )
        args["risk_tranches"] = [args["risk_tranches"][0]]
        args["reentry_obligations"] = [args["reentry_obligations"][0]]

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(50, document["subjective_tier_cap_units"])
        self.assertEqual("0.5", document["distributable_reference_risk_budget"])
        self.assertEqual(
            "LOW", document["cluster_risk_allocations"][0]["aggregate_tier"]
        )

    def test_round_trip_is_risk_first_and_non_executable(self) -> None:
        args = _flat_args()
        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(
            verify_v32_dynamic_action_plan_v1(
                document, dynamic_research_state=args["dynamic_research_state"]
            ),
            document["dynamic_action_plan_digest"],
        )
        self.assertEqual(document["subjective_tier_cap_units"], 100)
        self.assertEqual(
            document["directional_subjective_tier_cap_units"],
            {"LONG": 100, "SHORT": 50},
        )
        self.assertEqual(
            document["residual_uncertainty_tier"], "EXTREME_UNCERTAINTY"
        )
        self.assertEqual(document["residual_uncertainty_cap_units"], 100)
        self.assertEqual(document["risk_bottleneck_cap_units"], 100)
        self.assertEqual(document["distributable_reference_risk_budget"], "1")
        self.assertEqual(
            document["cluster_risk_allocations"],
            [
                {
                    "cluster_id": "c-long",
                    "aggregate_tier": "HIGH",
                    "allocation_units": 2,
                    "pre_modifier_reference_risk": "0.666667",
                    "path_modifier_risk_cap_units": 100,
                    "reference_risk": "0.666667",
                },
                {
                    "cluster_id": "c-short",
                    "aggregate_tier": "LOW",
                    "allocation_units": 1,
                    "pre_modifier_reference_risk": "0.333333",
                    "path_modifier_risk_cap_units": 100,
                    "reference_risk": "0.333333",
                },
            ],
        )
        tranche_map = {row["tranche_id"]: row for row in document["risk_tranches"]}
        self.assertEqual(tranche_map["t-long"]["unit_loss_reference"], "0.6")
        self.assertEqual(tranche_map["t-long"]["derived_reference_scale"], "1.111111")
        self.assertEqual(tranche_map["t-short"]["derived_reference_scale"], "0.555555")
        self.assertFalse(document["executable"])
        self.assertEqual(document["account_claim"], "NONE_NO_ACCOUNT_STATE")
        self.assertEqual(document["fill_claim"], "NONE_NO_FILL_MODEL")
        self.assertEqual(document["pnl_claim"], "NONE_NO_PNL_MODEL")
        self.assertEqual(
            document["market_money_claim"],
            "FORBIDDEN_FLOATING_GAIN_REMAINS_AT_RISK",
        )
        self.assertEqual(
            document["future_execution_hazard"]["stop_semantics"],
            "STOP_TRIGGER_IS_NOT_FILL_GAP_SLIPPAGE_REJECTION_REMAIN",
        )
        self.assertEqual(document["current_executable_reference_risk_budget"], "0")
        self.assertEqual(
            document["execution_gate"]["current_execution_eligibility"],
            "BLOCKED_PUBLIC_RESEARCH_ONLY",
        )
        self.assertFalse(document["execution_gate"]["order_submission_allowed"])

    def test_terminal_plan_states_cannot_remain_selectable(self) -> None:
        for terminal_state in ("CANCELLED", "EXPIRED", "SUPERSEDED"):
            top_level = _flat_args()
            top_level["plan_state"] = terminal_state
            with self.subTest(
                scope="plan", terminal_state=terminal_state
            ), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_PLAN_STATE_INVALID",
            ):
                build_v32_dynamic_action_plan_v1(**top_level)

            candidate_level = _flat_args()
            next(
                row
                for row in candidate_level["candidates"]
                if row["candidate_id"] == "open-long"
            )["plan_state"] = terminal_state
            with self.subTest(
                scope="candidate", terminal_state=terminal_state
            ), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_CANDIDATE_PLAN_STATE_INVALID",
            ):
                build_v32_dynamic_action_plan_v1(**candidate_level)

    def test_opposing_path_modifier_caps_only_affected_candidate_risk(self) -> None:
        args = _flat_args(
            dynamic_state=_dynamic_state_with_modifier(effect="OPPOSES_PATH")
        )

        document = build_v32_dynamic_action_plan_v1(**args)

        assessment = next(
            row
            for row in document["path_modifier_candidate_assessments"]
            if row["candidate_id"] == "open-long"
        )
        self.assertEqual(assessment["risk_cap_units"], 50)
        allocation = {
            row["cluster_id"]: row for row in document["cluster_risk_allocations"]
        }
        self.assertEqual(allocation["c-long"]["pre_modifier_reference_risk"], "0.666667")
        self.assertEqual(allocation["c-long"]["reference_risk"], "0.333333")
        self.assertEqual(allocation["c-short"]["reference_risk"], "0.333333")
        self.assertEqual(document["pre_modifier_reference_risk_budget"], "1")
        self.assertEqual(document["distributable_reference_risk_budget"], "0.666666")
        self.assertEqual(document["selected_candidate_reference_risk_budget"], "0.333333")

    def test_active_invalidating_modifier_must_block_new_risk(self) -> None:
        args = _flat_args(
            dynamic_state=_dynamic_state_with_modifier(effect="INVALIDATES_PATH")
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "DERIVED_HARD_GATE_MUST_BLOCK_NEW_RISK",
        ):
            build_v32_dynamic_action_plan_v1(**args)

        long_candidate = next(
            row for row in args["candidates"] if row["candidate_id"] == "open-long"
        )
        long_candidate.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "PATH_MODIFIER_INVALIDATION",
                "blocking_evidence_refs": ["source:modifier-state-long"],
                "risk_tranche_id": None,
            }
        )
        args["risk_tranches"] = [
            row for row in args["risk_tranches"] if row["candidate_id"] != "open-long"
        ]
        args["reentry_obligations"] = [
            row
            for row in args["reentry_obligations"]
            if row["source_tranche_id"] != "t-long"
        ]
        args["selected_candidate_id"] = "open-short"
        args["alternative_candidate_rank"] = ["open-long", "wait"]

        document = build_v32_dynamic_action_plan_v1(**args)

        assessment = next(
            row
            for row in document["path_modifier_candidate_assessments"]
            if row["candidate_id"] == "open-long"
        )
        self.assertEqual(assessment["risk_cap_units"], 0)
        self.assertEqual(
            assessment["invalidating_modifier_ids"], ["modifier-state-long"]
        )
        self.assertNotIn(
            "c-long", {row["cluster_id"] for row in document["cluster_risk_allocations"]}
        )

    def test_unknown_modifier_cannot_behave_as_confirmed_support(self) -> None:
        args = _flat_args(
            dynamic_state=_dynamic_state_with_modifier(
                effect="SUPPORTS_PATH", status="UNKNOWN"
            )
        )

        document = build_v32_dynamic_action_plan_v1(**args)

        assessment = next(
            row
            for row in document["path_modifier_candidate_assessments"]
            if row["candidate_id"] == "open-long"
        )
        self.assertEqual(assessment["risk_cap_units"], 50)
        self.assertEqual(document["selected_candidate_reference_risk_budget"], "0.333333")

    def test_real_execution_max_loss_unknown_cannot_delete_research_direction(self) -> None:
        state = _dynamic_state()
        unknowns = deepcopy(state["unknowns"])
        next(row for row in unknowns if row["unknown_id"] == "u-loss")[
            "dependency_refs"
        ] = ["dependency:state"]
        blocked_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=unknowns,
            zones=state["zones"],
            hypotheses=state["hypotheses"],
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        args = _flat_args(dynamic_state=blocked_state)
        document = build_v32_dynamic_action_plan_v1(**args)
        self.assertGreater(
            Decimal(document["selected_candidate_reference_risk_budget"]),
            Decimal("0"),
        )

        for candidate in args["candidates"]:
            if candidate["action_kind"] == "OPEN_PROBE":
                candidate.update(
                    {
                        "feasibility": "BLOCKED",
                        "block_reason": "MAX_LOSS",
                        "blocking_unknown_ids": ["u-loss"],
                        "blocking_evidence_refs": ["dependency:state"],
                        "risk_tranche_id": None,
                    }
                )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]

        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "REAL_EXECUTION_MAX_LOSS_CANNOT_BLOCK_RESEARCH",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_objective_quality_is_derived_and_rejects_agent_input(self) -> None:
        args = _flat_args()
        document = build_v32_dynamic_action_plan_v1(**args)
        assessment = document["risk_availability_assessment"]
        self.assertEqual(
            "COMPLETE", assessment["hypothesis_evidence_chain_coverage"]
        )
        self.assertEqual(
            [], assessment["missing_hypothesis_evidence_requirements"]
        )
        self.assertEqual(
            "UNKNOWN_NOT_IN_DYNAMIC_STATE",
            assessment["source_admission_coverage_status"],
        )
        self.assertEqual("ALLOWED_NO_EXTRA_SCALAR", assessment["regime_gate_status"])
        self.assertEqual(
            "PASSED_BY_TYPED_CANDIDATE_AND_TRANCHE_VALIDATION",
            assessment["geometry_gate_status"],
        )
        self.assertIn(
            "NO_AGENT_QUALITY", assessment["derivation_policy"]
        )

        args["risk_availability_assessment"] = _risk_availability()
        with self.assertRaisesRegex(TypeError, "risk_availability_assessment"):
            build_v32_dynamic_action_plan_v1(**args)

    def test_nondirectional_regime_forces_zero_new_directional_risk(self) -> None:
        for regime in (
            "NEUTRAL",
            "CHOPPY",
            "VOLATILITY_WITHOUT_DIRECTION",
            "TRANSITION",
            "OTHER",
            "UNKNOWN",
        ):
            with self.subTest(regime=regime):
                state = _dynamic_state_with_regime(regime)
                args = _flat_args(dynamic_state=state)
                regime_refs = sorted(
                    state["market_regime_state"]["evidence_refs"]
                    + state["market_regime_state"]["counter_evidence_refs"]
                    + state["market_regime_state"]["transition_evidence_refs"]
                )
                for candidate in args["candidates"]:
                    if candidate["action_kind"] == "WAIT":
                        continue
                    candidate.update(
                        {
                            "plan_state": "CONDITIONAL",
                            "feasibility": "BLOCKED",
                            "block_reason": "MARKET_REGIME_NON_DIRECTIONAL",
                            "blocking_evidence_refs": regime_refs,
                            "risk_tranche_id": None,
                        }
                    )
                args["risk_tranches"] = []
                args["reentry_obligations"] = []
                args["selected_candidate_id"] = "wait"
                args["alternative_candidate_rank"] = ["open-long", "open-short"]
                document = build_v32_dynamic_action_plan_v1(**args)
                self.assertEqual("0", document["distributable_reference_risk_budget"])
                self.assertEqual([], document["risk_tranches"])
                self.assertEqual([], document["cluster_risk_allocations"])
                self.assertEqual(
                    1, len(document["research_breakout_trigger_pairs"])
                )
                pair = document["research_breakout_trigger_pairs"][0]
                self.assertEqual("CLOSED_CANDLES_15M", pair["source_component_id"])
                self.assertEqual("15M", pair["timeframe"])
                self.assertEqual("close", pair["observed_field"])
                self.assertTrue(pair["closed_bar_required"])
                self.assertEqual(1, pair["required_consecutive_closed_bars"])
                self.assertEqual(document["as_of"], pair["valid_from"])
                self.assertEqual(HORIZON, pair["expires_at"])
                self.assertEqual(
                    "RESEARCH_REANALYSIS_ONLY_NO_AUTOMATIC_ACTION_OR_RISK",
                    pair["match_effect"],
                )
                self.assertEqual("NONE_NO_ORDER", pair["order_claim"])
                self.assertEqual("NONE_NO_OCO_ORDER", pair["oco_claim"])
                self.assertFalse(pair["executable"])
                legs = {leg["direction"]: leg for leg in pair["legs"]}
                zone = state["zones"][0]
                self.assertEqual(
                    {
                        "LONG": (
                            "upper_bound",
                            zone["upper_bound"],
                            "CLOSE_GT_THRESHOLD",
                        ),
                        "SHORT": (
                            "lower_bound",
                            zone["lower_bound"],
                            "CLOSE_LT_THRESHOLD",
                        ),
                    },
                    {
                        direction: (
                            leg["boundary_field"],
                            leg["threshold_value"],
                            leg["comparator"],
                        )
                        for direction, leg in legs.items()
                    },
                )

    def test_research_breakout_pair_is_system_derived_and_tamper_evident(
        self,
    ) -> None:
        directional = build_v32_dynamic_action_plan_v1(**_flat_args())
        self.assertEqual([], directional["research_breakout_trigger_pairs"])

        state = _dynamic_state_with_regime("CHOPPY")
        args = _flat_args(dynamic_state=state)
        regime_refs = sorted(
            state["market_regime_state"]["evidence_refs"]
            + state["market_regime_state"]["counter_evidence_refs"]
            + state["market_regime_state"]["transition_evidence_refs"]
        )
        for candidate in args["candidates"]:
            if candidate["action_kind"] == "WAIT":
                continue
            candidate.update(
                {
                    "plan_state": "CONDITIONAL",
                    "feasibility": "BLOCKED",
                    "block_reason": "MARKET_REGIME_NON_DIRECTIONAL",
                    "blocking_evidence_refs": regime_refs,
                    "risk_tranche_id": None,
                }
            )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        document = build_v32_dynamic_action_plan_v1(**args)
        for field, value in (
            ("threshold_value", "999999"),
            ("comparator", "CLOSE_GTE_THRESHOLD"),
        ):
            with self.subTest(field=field):
                tampered = deepcopy(document)
                tampered["research_breakout_trigger_pairs"][0]["legs"][0][
                    field
                ] = value
                tampered = self_digest(
                    tampered, "dynamic_action_plan_digest"
                )
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "RECONSTRUCTION_MISMATCH",
                ):
                    verify_v32_dynamic_action_plan_v1(
                        tampered, dynamic_research_state=state
                    )

    def test_reference_parent_id_and_geometry_are_domain_bound(self) -> None:
        valid = build_v32_dynamic_action_plan_v1(**_long_intent_args())
        self.assertEqual(
            "prior-long-tranche",
            valid["reference_tranche_state"]["tranche_id"],
        )

        wrong_id = _long_intent_args()
        wrong_id["reference_tranche_state"]["tranche_id"] = "invented-parent"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "REFERENCE_TRANCHE_CANDIDATE_BINDING_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**wrong_id)

        wrong_geometry = _long_intent_args()
        wrong_geometry["reference_tranche_state"]["entry_reference"] = "90"
        wrong_geometry["reference_tranche_state"][
            "protective_stop_reference"
        ] = "85"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "REFERENCE_TRANCHE_GEOMETRY_BINDING_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**wrong_geometry)

        reused_parent_id = _long_intent_args()
        next(
            row
            for row in reused_parent_id["candidates"]
            if row["candidate_id"] == "add-long"
        )["risk_tranche_id"] = "prior-long-tranche"
        next(
            row
            for row in reused_parent_id["risk_tranches"]
            if row["candidate_id"] == "add-long"
        )["tranche_id"] = "prior-long-tranche"
        next(
            row
            for row in reused_parent_id["reentry_obligations"]
            if row["obligation_id"] == "o-add"
        )["source_tranche_id"] = "prior-long-tranche"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "NEW_TRANCHE_ID_MUST_DIFFER_FROM_PARENT",
        ):
            build_v32_dynamic_action_plan_v1(**reused_parent_id)

        expired_parent = _long_intent_args()
        expired_parent["reference_tranche_state"]["valid_until"] = AS_OF
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "REFERENCE_TRANCHE_STATE_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**expired_parent)

    def test_risk_candidate_cannot_smuggle_opposite_or_unclustered_hypothesis(
        self,
    ) -> None:
        args = _flat_args()
        next(
            row
            for row in args["candidates"]
            if row["candidate_id"] == "open-long"
        )["hypothesis_ids"].append("h-short")
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "RISK_CLUSTER_HYPOTHESIS_BINDING_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_nondirectional_risk_plans_require_typed_breakout_boundary(self) -> None:
        state = _dynamic_state_with_regime("CHOPPY", zone_role="SUPPORT")
        args = _flat_args(dynamic_state=state)
        regime_refs = sorted(
            state["market_regime_state"]["evidence_refs"]
            + state["market_regime_state"]["counter_evidence_refs"]
            + state["market_regime_state"]["transition_evidence_refs"]
        )
        for candidate in args["candidates"]:
            if candidate["action_kind"] == "WAIT":
                continue
            candidate.update(
                {
                    "plan_state": "CONDITIONAL",
                    "feasibility": "BLOCKED",
                    "block_reason": "MARKET_REGIME_NON_DIRECTIONAL",
                    "blocking_evidence_refs": regime_refs,
                    "risk_tranche_id": None,
                }
            )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "NONDIRECTIONAL_BREAKOUT_BOUNDARY_REQUIRED",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_structured_range_remains_conditionally_actionable(self) -> None:
        document = build_v32_dynamic_action_plan_v1(
            **_flat_args(dynamic_state=_dynamic_state_with_regime("RANGE"))
        )
        self.assertGreater(
            Decimal(document["distributable_reference_risk_budget"]), Decimal("0")
        )

    def test_reentry_churn_scope_is_exactly_bound_to_run_and_instrument(self) -> None:
        for field, value in (
            ("budget_id", "agent-selected-budget"),
            ("churn_scope", "CLUSTER_LOCAL"),
            ("instrument", "ETH-USDT-SWAP"),
            ("window_policy", "ROLLING_AGENT_RESETTABLE"),
        ):
            with self.subTest(field=field):
                args = _flat_args()
                args["reentry_budget_state"][field] = value
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "V32_ACTION_REENTRY_INSTRUMENT_CHURN_SCOPE_INVALID",
                ):
                    build_v32_dynamic_action_plan_v1(**args)

    def test_agent_cannot_override_fixed_raw_reference_envelope(self) -> None:
        for raw_budget in ("0.4", "90"):
            with self.subTest(raw_budget=raw_budget):
                args = _flat_args()
                args["reference_risk_unit_budget"] = raw_budget
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "V32_ACTION_REFERENCE_RISK_ENVELOPE_INVALID",
                ):
                    build_v32_dynamic_action_plan_v1(**args)

    def test_candidate_horizon_and_reentry_cannot_outlive_supporting_thesis(self) -> None:
        state = _dynamic_state()
        hypotheses = deepcopy(state["hypotheses"])
        next(row for row in hypotheses if row["hypothesis_id"] == "h-long")[
            "expires_at"
        ] = "2026-08-07T00:30:00Z"
        short_lived_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=state["zones"],
            hypotheses=hypotheses,
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        args = _flat_args(dynamic_state=short_lived_state)
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "HORIZON_EXCEEDS_SUPPORTING_HYPOTHESIS_EXPIRY",
        ):
            build_v32_dynamic_action_plan_v1(**args)

        next(row for row in args["candidates"] if row["candidate_id"] == "open-long")[
            "horizon_at"
        ] = "2026-08-07T00:20:00Z"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "REENTRY_TIME_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**args)

        state = _dynamic_state()
        zones = deepcopy(state["zones"])
        zones[0]["expires_at"] = "2026-08-07T00:30:00Z"
        short_lived_zone_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=zones,
            hypotheses=state["hypotheses"],
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "HORIZON_EXCEEDS_SUPPORTING_ZONE_EXPIRY",
        ):
            build_v32_dynamic_action_plan_v1(
                **_flat_args(dynamic_state=short_lived_zone_state)
            )

        zones[0]["expires_at"] = "2026-08-06T23:59:30Z"
        retired_zone_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=zones,
            hypotheses=state["hypotheses"],
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "RETIRED_ZONE_CANNOT_SUPPORT_CANDIDATE",
        ):
            build_v32_dynamic_action_plan_v1(
                **_flat_args(dynamic_state=retired_zone_state)
            )

    def test_denominator_trap_does_not_give_lone_low_tier_full_budget(self) -> None:
        state = _dynamic_state_with_modifier(
            effect="INVALIDATES_PATH",
            modifier_id="modifier-short-geometry-owner",
            dynamic_state=_dynamic_state(long_tier="LOW", short_tier="LOW"),
            target_hypothesis_id="h-short",
        )
        args = _flat_args(dynamic_state=state)
        short = next(row for row in args["candidates"] if row["candidate_id"] == "open-short")
        short.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "PATH_MODIFIER_INVALIDATION",
                "blocking_evidence_refs": ["source:modifier-short-geometry-owner"],
                "risk_tranche_id": None,
            }
        )
        args["risk_tranches"] = [args["risk_tranches"][0]]
        args["reentry_obligations"] = [args["reentry_obligations"][0]]

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(document["subjective_tier_cap_units"], 50)
        self.assertEqual(document["distributable_reference_risk_budget"], "0.5")
        self.assertEqual(document["cluster_risk_allocations"][0]["reference_risk"], "0.5")

    def test_terminal_hypothesis_cannot_support_new_risk(self) -> None:
        state = _dynamic_state()
        hypotheses = deepcopy(state["hypotheses"])
        clusters = deepcopy(state["dependency_clusters"])
        next(row for row in hypotheses if row["hypothesis_id"] == "h-long")[
            "status"
        ] = "FALSIFIED"
        next(row for row in hypotheses if row["hypothesis_id"] == "h-long")[
            "subjective_plausibility_tier"
        ] = "EXTREME_UNCERTAINTY"
        next(row for row in clusters if row["cluster_id"] == "c-long")[
            "aggregate_tier"
        ] = "EXTREME_UNCERTAINTY"
        terminal_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=state["zones"],
            hypotheses=hypotheses,
            path_modifiers=state["path_modifiers"],
            dependency_clusters=clusters,
        )
        args = _flat_args(dynamic_state=terminal_state)

        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_TERMINAL_HYPOTHESIS_CANNOT_SUPPORT_NEW_RISK",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_evidence_chain_diagnostic_does_not_scale_residual_risk(self) -> None:
        state = _dynamic_state(other_tier="LOW", unknown_tier="LOW")
        hypotheses = deepcopy(state["hypotheses"])
        next(row for row in hypotheses if row["hypothesis_id"] == "h-short")[
            "opposing_refs"
        ] = []
        partial_state = build_v32_dynamic_research_state_v1(
            run_id=state["run_id"],
            cycle_index=state["cycle_index"],
            as_of=state["as_of"],
            frame_mode=state["frame_mode"],
            previous_state_digest=state["previous_state_digest"],
            market_regime_state=state["market_regime_state"],
            unknowns=state["unknowns"],
            zones=state["zones"],
            hypotheses=hypotheses,
            path_modifiers=state["path_modifiers"],
            dependency_clusters=state["dependency_clusters"],
        )
        args = _flat_args(dynamic_state=partial_state)

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(
            "INCOMPLETE",
            document["risk_availability_assessment"][
                "hypothesis_evidence_chain_coverage"
            ],
        )
        self.assertEqual(document["subjective_tier_cap_units"], 100)
        self.assertEqual(document["residual_uncertainty_tier"], "LOW")
        self.assertEqual(document["residual_uncertainty_cap_units"], 50)
        self.assertEqual(document["risk_bottleneck_cap_units"], 50)
        self.assertEqual(document["distributable_reference_risk_budget"], "0.5")
        self.assertEqual(
            sum(
                (
                    Decimal(row["reference_risk"])
                    for row in document["cluster_risk_allocations"]
                ),
                Decimal("0"),
            ),
            Decimal("0.5"),
        )

    def test_residual_uncertainty_zero_budget_is_domain_owned_and_exact(self) -> None:
        state = _dynamic_state(other_tier="HIGH", unknown_tier="HIGH")
        args = _flat_args(dynamic_state=state)
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(0, document["residual_uncertainty_cap_units"])
        self.assertEqual([], document["cluster_risk_allocations"])
        for candidate in document["candidates"]:
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS:
                self.assertEqual("BLOCKED", candidate["feasibility"])
                self.assertEqual(
                    "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
                    candidate["block_reason"],
                )

        forged = _flat_args(dynamic_state=_dynamic_state())
        forged_long = next(
            row
            for row in forged["candidates"]
            if row["candidate_id"] == "open-long"
        )
        forged_long.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        forged["risk_tranches"] = [
            row
            for row in forged["risk_tranches"]
            if row["candidate_id"] != "open-long"
        ]
        forged["reentry_obligations"] = [
            row
            for row in forged["reentry_obligations"]
            if row["obligation_id"] != "o-long"
        ]
        forged["selected_candidate_id"] = "open-short"
        forged["alternative_candidate_rank"] = ["open-long", "wait"]
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_RISK_QUANTUM_BLOCK_WITHOUT_CAUSE",
        ):
            build_v32_dynamic_action_plan_v1(**forged)

        wrong_refs = deepcopy(args)
        for candidate in wrong_refs["candidates"]:
            if candidate["action_kind"] in RISK_INCREASING_ACTIONS:
                candidate.update(
                    {
                        "feasibility": "BLOCKED",
                        "block_reason": "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
                        "blocking_unknown_ids": [],
                        "blocking_evidence_refs": ["source:unrelated"],
                        "risk_tranche_id": None,
                    }
                )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_RISK_QUANTUM_BLOCK_WITHOUT_CAUSE",
        ):
            build_v32_dynamic_action_plan_v1(**wrong_refs)

        for blocked_id in ("hold-long", "reduce-long"):
            management = _long_intent_args()
            management["dynamic_research_state"] = state
            blocked = next(
                row
                for row in management["candidates"]
                if row["candidate_id"] == blocked_id
            )
            hypotheses = {
                row["hypothesis_id"]: row for row in state["hypotheses"]
            }
            blocked.update(
                {
                    "feasibility": "BLOCKED",
                    "block_reason": "RISK_BUDGET_BELOW_CLUSTER_QUANTUM",
                    "blocking_evidence_refs": sorted(
                        {
                            ref
                            for hypothesis_id in blocked["hypothesis_ids"]
                            for ref in hypotheses[hypothesis_id]["source_refs"]
                        }
                    ),
                }
            )
            management["risk_tranches"] = []
            management["reentry_obligations"] = []
            management["selected_candidate_id"] = (
                "close-long" if blocked_id != "close-long" else "hold-long"
            )
            management["alternative_candidate_rank"] = [
                row["candidate_id"]
                for row in management["candidates"]
                if row["candidate_id"]
                != management["selected_candidate_id"]
            ]
            with self.subTest(blocked_management_candidate=blocked_id), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_RISK_QUANTUM_BLOCK_WITHOUT_CAUSE",
            ):
                build_v32_dynamic_action_plan_v1(**management)

    def test_unowned_soft_reason_cannot_delete_one_direction(self) -> None:
        for reason, refs in (
            ("COST_OR_LIQUIDITY", ["agent-cost-opinion"]),
            ("GEOMETRY", ["agent-geometry-opinion"]),
        ):
            args = _flat_args()
            short = next(
                row
                for row in args["candidates"]
                if row["candidate_id"] == "open-short"
            )
            short.update(
                {
                    "feasibility": "BLOCKED",
                    "block_reason": reason,
                    "blocking_evidence_refs": refs,
                    "risk_tranche_id": None,
                }
            )
            args["risk_tranches"] = [
                row
                for row in args["risk_tranches"]
                if row["candidate_id"] != "open-short"
            ]
            args["reentry_obligations"] = [
                row
                for row in args["reentry_obligations"]
                if row["obligation_id"] != "o-short"
            ]
            with self.subTest(reason=reason), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_UNOWNED_FEASIBILITY_BLOCK_FORBIDDEN",
            ):
                build_v32_dynamic_action_plan_v1(**args)

    def test_no_new_evidence_is_a_typed_block_not_a_forced_entry(self) -> None:
        args = _long_intent_args()
        for candidate in args["candidates"]:
            if candidate["action_kind"] not in {"ADD", "REVERSE"}:
                continue
            candidate.update(
                {
                    "feasibility": "BLOCKED",
                    "block_reason": "NO_NEW_EVIDENCE",
                    "blocking_evidence_refs": [
                        "no-new-current-pit-evidence-since-predecessor"
                    ],
                    "blocking_unknown_ids": [],
                    "new_evidence_refs": [],
                    "risk_tranche_id": None,
                }
            )
        args["risk_tranches"] = []
        args["reentry_obligations"] = []
        args["selected_candidate_id"] = "hold-long"
        args["alternative_candidate_rank"] = [
            "add-long",
            "reduce-long",
            "close-long",
            "reverse-short",
        ]

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual("hold-long", document["selected_candidate_id"])
        self.assertEqual([], document["cluster_risk_allocations"])
        self.assertEqual("0", document["selected_candidate_reference_risk_budget"])
        for candidate_id in ("add-long", "reverse-short"):
            candidate = next(
                row
                for row in document["candidates"]
                if row["candidate_id"] == candidate_id
            )
            self.assertEqual("NO_NEW_EVIDENCE", candidate["block_reason"])
            self.assertEqual([], candidate["new_evidence_refs"])

    def test_multiple_low_tiers_never_sum_into_high_confidence(self) -> None:
        result = compute_v32_effective_reference_risk_v1(
            raw_reference_risk_budget="1",
            eligible_cluster_tiers=["LOW"] * 5,
            eligible_cluster_directions=["LONG"] * 5,
            residual_uncertainty_cap_units=100,
        )

        self.assertEqual(result["subjective_tier_cap_units"], 50)
        self.assertEqual(
            result["directional_subjective_tier_cap_units"],
            {"LONG": 50, "SHORT": 0},
        )
        self.assertEqual(result["risk_bottleneck_cap_units"], 50)
        self.assertEqual(result["effective_reference_risk_budget"], "0.5")

    def test_opposed_direction_support_does_not_add(self) -> None:
        result = compute_v32_effective_reference_risk_v1(
            raw_reference_risk_budget="1",
            eligible_cluster_tiers=["HIGH", "LOW", "LOW", "LOW"],
            eligible_cluster_directions=["LONG", "LONG", "SHORT", "SHORT"],
            residual_uncertainty_cap_units=100,
        )

        self.assertEqual(
            result["directional_subjective_tier_cap_units"],
            {"LONG": 100, "SHORT": 50},
        )
        self.assertEqual(result["subjective_tier_cap_units"], 100)
        self.assertEqual(result["effective_reference_risk_budget"], "1")

    def test_opposite_high_cannot_lift_low_direction_above_its_cap(self) -> None:
        clusters = {
            "long-high": {"aggregate_tier": "HIGH", "direction": "LONG"},
            **{
                f"short-low-{index}": {
                    "aggregate_tier": "LOW",
                    "direction": "SHORT",
                }
                for index in range(5)
            },
        }
        effective = compute_v32_effective_reference_risk_v1(
            raw_reference_risk_budget="1",
            eligible_cluster_tiers=["HIGH", *(["LOW"] * 5)],
            eligible_cluster_directions=["LONG", *(["SHORT"] * 5)],
            residual_uncertainty_cap_units=100,
        )

        allocations = _allocate_cluster_risk(
            reference_risk_budget=Decimal(
                effective["effective_reference_risk_budget"]
            ),
            raw_reference_risk_budget=Decimal("1"),
            directional_subjective_tier_cap_units=effective[
                "directional_subjective_tier_cap_units"
            ],
            cluster_ids=list(clusters),
            clusters=clusters,
        )
        direction_totals = {
            direction: sum(
                (
                    Decimal(row["reference_risk"])
                    for row in allocations
                    if clusters[row["cluster_id"]]["direction"] == direction
                ),
                Decimal("0"),
            )
            for direction in ("LONG", "SHORT")
        }

        self.assertEqual(
            len(allocations), len({row["cluster_id"] for row in allocations})
        )
        self.assertTrue(
            all(
                Decimal(row["reference_risk"]) % Decimal("0.000001") == 0
                for row in allocations
            )
        )
        self.assertEqual(sum(direction_totals.values()), Decimal("1"))
        self.assertLessEqual(direction_totals["LONG"], Decimal("1"))
        self.assertLessEqual(direction_totals["SHORT"], Decimal("0.5"))
        self.assertEqual(
            direction_totals,
            {"LONG": Decimal("0.666667"), "SHORT": Decimal("0.333333")},
        )

    def test_direction_allocation_is_invariant_to_same_side_cluster_count(self) -> None:
        def direction_totals(short_cluster_count: int) -> dict[str, Decimal]:
            clusters = {
                "long-low": {"aggregate_tier": "LOW", "direction": "LONG"},
                **{
                    f"short-low-{index}": {
                        "aggregate_tier": "LOW",
                        "direction": "SHORT",
                    }
                    for index in range(short_cluster_count)
                },
            }
            effective = compute_v32_effective_reference_risk_v1(
                raw_reference_risk_budget="1",
                eligible_cluster_tiers=["LOW"] * len(clusters),
                eligible_cluster_directions=[
                    "LONG",
                    *(["SHORT"] * short_cluster_count),
                ],
                residual_uncertainty_cap_units=100,
            )
            allocations = _allocate_cluster_risk(
                reference_risk_budget=Decimal(
                    effective["effective_reference_risk_budget"]
                ),
                raw_reference_risk_budget=Decimal("1"),
                directional_subjective_tier_cap_units=effective[
                    "directional_subjective_tier_cap_units"
                ],
                cluster_ids=list(clusters),
                clusters=clusters,
            )
            return {
                direction: sum(
                    (
                        Decimal(row["reference_risk"])
                        for row in allocations
                        if clusters[row["cluster_id"]]["direction"] == direction
                    ),
                    Decimal("0"),
                )
                for direction in ("LONG", "SHORT")
            }

        baseline = direction_totals(1)
        replicated = direction_totals(10)

        self.assertEqual(
            baseline,
            {"LONG": Decimal("0.25"), "SHORT": Decimal("0.25")},
        )
        self.assertEqual(replicated, baseline)

    def test_support_and_residual_use_min_bottleneck(self) -> None:
        result = compute_v32_effective_reference_risk_v1(
            raw_reference_risk_budget="1",
            eligible_cluster_tiers=["HIGH", "LOW"],
            eligible_cluster_directions=["LONG", "SHORT"],
            residual_uncertainty_cap_units=50,
        )

        self.assertEqual(result["subjective_tier_cap_units"], 100)
        self.assertEqual(result["risk_bottleneck_cap_units"], 50)
        self.assertEqual(result["effective_reference_risk_budget"], "0.5")
        self.assertNotEqual(result["effective_reference_risk_budget"], "0.3")

        for arbitrary_cap in (35, 75):
            with self.subTest(arbitrary_cap=arbitrary_cap), self.assertRaisesRegex(
                V32DynamicActionPlanError, "V32_ACTION_RISK_AVAILABILITY_INVALID"
            ):
                compute_v32_effective_reference_risk_v1(
                    raw_reference_risk_budget="1",
                    eligible_cluster_tiers=["HIGH"],
                    eligible_cluster_directions=["LONG"],
                    residual_uncertainty_cap_units=arbitrary_cap,
                )

    def test_wait_must_dominate_every_eligible_risk_candidate(self) -> None:
        args = _flat_args()
        args["selected_candidate_id"] = "wait"
        args["alternative_candidate_rank"] = ["open-long", "open-short"]
        args["wait_assessment"] = _wait(
            [
                {
                    "candidate_id": candidate_id,
                    "dominance_reason": "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE",
                    "evidence_refs": [f"distinguishing-observation:{candidate_id}"],
                    "rationale": "one bounded observation dominates immediate reference risk",
                }
                for candidate_id in ("open-long", "open-short")
            ]
        )
        document = build_v32_dynamic_action_plan_v1(**args)
        self.assertEqual(document["selected_candidate_id"], "wait")

        broken = deepcopy(args)
        broken["wait_assessment"]["dominance_comparisons"].pop()
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_WAIT_DOMINANCE_COVERAGE_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**broken)

        generic = deepcopy(args)
        generic["wait_assessment"]["dominance_comparisons"][0][
            "dominance_reason"
        ] = "MARKET_UNCERTAIN"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_WAIT_GENERIC_REASON_FORBIDDEN"
        ):
            build_v32_dynamic_action_plan_v1(**generic)

    def test_add_requires_new_evidence_and_forbids_averaging_down(self) -> None:
        args = _long_intent_args()
        document = build_v32_dynamic_action_plan_v1(**args)
        self.assertEqual(document["selected_candidate_id"], "add-long")

        averaging_down = deepcopy(args)
        averaging_down["risk_tranches"][0]["conditional_entry_reference"] = "99"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_AVERAGING_DOWN_FORBIDDEN"
        ):
            build_v32_dynamic_action_plan_v1(**averaging_down)

        no_new_evidence = deepcopy(args)
        no_new_evidence["candidates"][0]["new_evidence_refs"] = []
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_ADD_NEW_EVIDENCE_REQUIRED"
        ):
            build_v32_dynamic_action_plan_v1(**no_new_evidence)

    def test_reverse_is_close_first_and_stop_never_expands_risk(self) -> None:
        args = _long_intent_args()
        atomic = deepcopy(args)
        reverse = next(row for row in atomic["candidates"] if row["action_kind"] == "REVERSE")
        reverse["close_first_candidate_id"] = None
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_REVERSE_SEQUENCE_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**atomic)

        wider_stop = deepcopy(args)
        wider_stop["risk_tranches"][0]["protective_stop_reference"] = "94"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_STOP_RISK_EXPANSION_FORBIDDEN"
        ):
            build_v32_dynamic_action_plan_v1(**wider_stop)

    def test_reentry_requires_conditional_obligation_and_new_budget(self) -> None:
        args = _flat_args()
        args["reference_context"] = "REENTRY_LONG_RESEARCH_INTENT"
        reenter = args["candidates"][0]
        reenter.update(
            {
                "candidate_id": "reenter-long",
                "action_kind": "REENTER",
                "reentry_obligation_id": "o-prior",
                "new_evidence_refs": ["fresh-reentry-trigger"],
            }
        )
        args["risk_tranches"][0]["candidate_id"] = "reenter-long"
        args["risk_tranches"][0]["entry_mode"] = "RETEST_OR_REENTRY"
        args["risk_tranches"][0]["new_evidence_refs"] = ["fresh-reentry-trigger"]
        args["reentry_obligations"].append(
            _obligation(
                "o-prior",
                "old-closed-tranche",
                "LONG",
                "h-long",
                "c-long",
                plan_state="CONDITIONAL",
            )
        )
        args["selected_candidate_id"] = "reenter-long"
        args["alternative_candidate_rank"] = ["open-short", "wait"]
        args["reentry_budget_state"] = _available_reentry_budget()

        document = build_v32_dynamic_action_plan_v1(**args)
        self.assertEqual(
            next(row for row in document["candidates"] if row["candidate_id"] == "reenter-long")[
                "action_kind"
            ],
            "REENTER",
        )

        same_cycle_budget = deepcopy(args)
        same_cycle_budget["reentry_budget_state"][
            "cumulative_reference_risk"
        ] = "0.75"
        bounded_reentry = build_v32_dynamic_action_plan_v1(**same_cycle_budget)
        self.assertEqual(
            "0.666667",
            bounded_reentry["selected_candidate_reference_risk_budget"],
        )
        self.assertLessEqual(
            Decimal(
                bounded_reentry["reentry_budget_state"][
                    "cumulative_reference_risk"
                ]
            )
            + Decimal(bounded_reentry["selected_candidate_reference_risk_budget"]),
            Decimal("2"),
        )

        invalid = deepcopy(args)
        next(
            row for row in invalid["reentry_obligations"] if row["obligation_id"] == "o-prior"
        )["requires_new_risk_budget"] = False
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_REENTRY_HISTORY_OR_BUDGET_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**invalid)

        false_available_block = deepcopy(args)
        false_available_reentry = next(
            row
            for row in false_available_block["candidates"]
            if row["candidate_id"] == "reenter-long"
        )
        false_available_reentry.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        false_available_block["risk_tranches"] = [
            row
            for row in false_available_block["risk_tranches"]
            if row["candidate_id"] != "reenter-long"
        ]
        false_available_block["reentry_obligations"] = [
            row
            for row in false_available_block["reentry_obligations"]
            if row["obligation_id"] != "o-long"
        ]
        false_available_block["selected_candidate_id"] = "wait"
        false_available_block["alternative_candidate_rank"] = [
            "reenter-long",
            "open-short",
        ]
        false_available_block["wait_assessment"] = _wait(
            [
                {
                    "candidate_id": "open-short",
                    "dominance_reason": "INFORMATION_VALUE_DOMINATES_UNTIL_DEADLINE",
                    "evidence_refs": ["distinguishing-observation:open-short"],
                    "rationale": "one bounded observation dominates immediate reference risk",
                }
            ]
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_BUDGET_BLOCK_WITHOUT_CAUSE",
        ):
            build_v32_dynamic_action_plan_v1(**false_available_block)

        exhausted = deepcopy(args)
        exhausted["reentry_budget_state"].update(
            {
                "attempts_used": 2,
                "cumulative_reference_risk": "1",
                "consecutive_failures": 2,
                "cooldown_until": REENTRY_WINDOW_EXPIRES,
                "status": "EXHAUSTED",
            }
        )
        exhausted_reentry = next(
            row
            for row in exhausted["candidates"]
            if row["candidate_id"] == "reenter-long"
        )
        exhausted_reentry.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        exhausted_short = next(
            row
            for row in exhausted["candidates"]
            if row["candidate_id"] == "open-short"
        )
        exhausted_short.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        exhausted["risk_tranches"] = []
        exhausted["reentry_obligations"] = [
            row
            for row in exhausted["reentry_obligations"]
            if row["obligation_id"] == "o-prior"
        ]
        exhausted["selected_candidate_id"] = "wait"
        exhausted["alternative_candidate_rank"] = [
            "reenter-long",
            "open-short",
        ]
        exhausted["wait_assessment"] = _wait()
        blocked_document = build_v32_dynamic_action_plan_v1(**exhausted)
        self.assertEqual(
            "REENTRY_COOLDOWN_OR_BUDGET",
            next(
                row
                for row in blocked_document["candidates"]
                if row["candidate_id"] == "reenter-long"
            )["block_reason"],
        )

        enlarged_failure_refs = deepcopy(exhausted)
        enlarged_reentry = next(
            row
            for row in enlarged_failure_refs["candidates"]
            if row["candidate_id"] == "reenter-long"
        )
        enlarged_reentry["blocking_evidence_refs"] = [
            "source:h-long",
            "source:h-short",
        ]
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_INSTRUMENT_CHURN_BUDGET_MUST_BLOCK",
        ):
            build_v32_dynamic_action_plan_v1(**enlarged_failure_refs)

        too_short = deepcopy(exhausted)
        too_short["reentry_budget_state"]["cooldown_until"] = EXPIRES
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_EXHAUSTION_COOLDOWN_ENDPOINT_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**too_short)

        too_long = deepcopy(exhausted)
        too_long["reentry_budget_state"]["cooldown_until"] = (
            "2026-08-08T00:00:01Z"
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_EXHAUSTION_COOLDOWN_ENDPOINT_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**too_long)

    def test_active_long_ledger_counts_opposite_open_probe_and_reverse_against_caps(
        self,
    ) -> None:
        open_probe = _flat_args()
        open_probe["reentry_budget_state"] = _available_reentry_budget()
        open_probe["selected_candidate_id"] = "open-short"
        open_probe["alternative_candidate_rank"] = ["open-long", "wait"]

        reverse = _long_intent_args()
        reverse["reentry_budget_state"] = _available_reentry_budget()
        reverse["selected_candidate_id"] = "reverse-short"
        reverse["alternative_candidate_rank"] = [
            "add-long",
            "hold-long",
            "reduce-long",
            "close-long",
        ]

        for action_kind, args in (
            ("OPEN_PROBE", open_probe),
            ("REVERSE", reverse),
        ):
            with self.subTest(action_kind=action_kind, gate="AVAILABLE"):
                document = build_v32_dynamic_action_plan_v1(**args)
                selected = next(
                    row
                    for row in document["candidates"]
                    if row["candidate_id"] == document["selected_candidate_id"]
                )
                self.assertEqual(action_kind, selected["action_kind"])
                self.assertEqual("SHORT", selected["direction"])
                self.assertEqual(
                    REENTRY_BUDGET_ID,
                    document["reentry_budget_state"]["budget_id"],
                )

            near_one_consumed = deepcopy(args)
            near_one_consumed["reentry_budget_state"][
                "cumulative_reference_risk"
            ] = "0.999999"
            with self.subTest(action_kind=action_kind, gate="CUMULATIVE_CAP"):
                bounded = build_v32_dynamic_action_plan_v1(**near_one_consumed)
                self.assertEqual(
                    "0.333333",
                    bounded["selected_candidate_reference_risk_budget"],
                )

            cooldown = deepcopy(args)
            cooldown["reentry_budget_state"].update(
                {"cooldown_until": HORIZON, "status": "COOLDOWN"}
            )
            with self.subTest(
                action_kind=action_kind, gate="COOLDOWN"
            ), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_INSTRUMENT_CHURN_BUDGET_MUST_BLOCK",
            ):
                build_v32_dynamic_action_plan_v1(**cooldown)

            exhausted = deepcopy(args)
            exhausted["reentry_budget_state"].update(
                {
                    "attempts_used": 2,
                    "cumulative_reference_risk": "1",
                    "consecutive_failures": 2,
                    "cooldown_until": REENTRY_WINDOW_EXPIRES,
                    "status": "EXHAUSTED",
                }
            )
            with self.subTest(
                action_kind=action_kind, gate="EXHAUSTED"
            ), self.assertRaisesRegex(
                V32DynamicActionPlanError,
                "V32_ACTION_INSTRUMENT_CHURN_BUDGET_MUST_BLOCK",
            ):
                build_v32_dynamic_action_plan_v1(**exhausted)

        selectable_variants = _flat_args()
        selectable_variants["reentry_budget_state"] = _available_reentry_budget()
        selectable_variants["reentry_budget_state"][
            "cumulative_reference_risk"
        ] = "0.6"
        for selected, expected_risk in (
            ("open-long", "0.666667"),
            ("open-short", "0.333333"),
        ):
            variant = deepcopy(selectable_variants)
            variant["selected_candidate_id"] = selected
            variant["alternative_candidate_rank"] = [
                candidate_id
                for candidate_id in ("open-long", "open-short", "wait")
                if candidate_id != selected
            ]
            with self.subTest(selected=selected, gate="VARIANT_CONSTRUCTIBLE"):
                built = build_v32_dynamic_action_plan_v1(**variant)
                self.assertEqual(
                    expected_risk,
                    built["selected_candidate_reference_risk_budget"],
                )

    def test_reentry_budget_envelope_window_and_exhausted_lock_are_frozen(self) -> None:
        for arbitrary_maximum in ("0.4", "10"):
            with self.subTest(arbitrary_maximum=arbitrary_maximum):
                args = _flat_args()
                args["reentry_budget_state"] = _available_reentry_budget()
                args["reentry_budget_state"][
                    "max_cumulative_reference_risk"
                ] = arbitrary_maximum
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "V32_ACTION_REENTRY_BUDGET_INVALID",
                ):
                    build_v32_dynamic_action_plan_v1(**args)

        for invalid_cumulative in ("0", "1.000001", "0.2500001"):
            with self.subTest(invalid_cumulative=invalid_cumulative):
                invalid_history = _flat_args()
                invalid_history["reentry_budget_state"] = (
                    _available_reentry_budget()
                )
                invalid_history["reentry_budget_state"][
                    "cumulative_reference_risk"
                ] = invalid_cumulative
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "V32_ACTION_REENTRY_BUDGET_INVALID",
                ):
                    build_v32_dynamic_action_plan_v1(**invalid_history)

        forged_zero_attempt_cooldown = _flat_args()
        forged_zero_attempt_cooldown["reentry_budget_state"] = (
            _available_reentry_budget()
        )
        forged_zero_attempt_cooldown["reentry_budget_state"].update(
            {
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 0,
                "cooldown_until": EXPIRES,
                "status": "COOLDOWN",
            }
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_BLOCK_STATE_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**forged_zero_attempt_cooldown)

        wrong_window = _flat_args()
        wrong_window["reentry_budget_state"] = _available_reentry_budget()
        wrong_window["reentry_budget_state"]["rolling_window_expires_at"] = EXPIRES
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_BUDGET_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**wrong_window)

        expired_cooldown = _flat_args()
        expired_cooldown["reentry_budget_state"] = _available_reentry_budget()
        expired_cooldown["reentry_budget_state"].update(
            {
                "rolling_window_started_at": "2026-08-06T00:00:00Z",
                "rolling_window_expires_at": AS_OF,
                "attempts_used": 2,
                "cumulative_reference_risk": "1",
                "consecutive_failures": 2,
                "cooldown_until": AS_OF,
                "status": "EXHAUSTED",
            }
        )
        disguised = next(
            row
            for row in expired_cooldown["candidates"]
            if row["candidate_id"] == "open-long"
        )
        disguised.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        opposite = next(
            row
            for row in expired_cooldown["candidates"]
            if row["candidate_id"] == "open-short"
        )
        opposite.update(
            {
                "feasibility": "BLOCKED",
                "block_reason": "REENTRY_COOLDOWN_OR_BUDGET",
                "blocking_evidence_refs": ["source:h-long"],
                "risk_tranche_id": None,
            }
        )
        expired_cooldown["risk_tranches"] = []
        expired_cooldown["reentry_obligations"] = []
        expired_cooldown["selected_candidate_id"] = "wait"
        expired_cooldown["alternative_candidate_rank"] = [
            "open-long",
            "open-short",
        ]
        expired_cooldown["wait_assessment"] = _wait()
        document = build_v32_dynamic_action_plan_v1(**expired_cooldown)
        self.assertEqual(
            "EXHAUSTED", document["reentry_budget_state"]["status"]
        )

        two_consecutive_stops = deepcopy(expired_cooldown)
        two_consecutive_stops["reentry_budget_state"].update(
            {
                "rolling_window_started_at": "2026-08-06T23:00:00Z",
                "rolling_window_expires_at": REENTRY_WINDOW_EXPIRES,
                "attempts_used": 1,
                "cumulative_reference_risk": "0.25",
                "consecutive_failures": 2,
                "cooldown_until": REENTRY_WINDOW_EXPIRES,
                "status": "EXHAUSTED",
            }
        )
        two_stop_document = build_v32_dynamic_action_plan_v1(
            **two_consecutive_stops
        )
        self.assertEqual(
            "EXHAUSTED",
            two_stop_document["reentry_budget_state"]["status"],
        )
        self.assertEqual(
            1,
            two_stop_document["reentry_budget_state"]["attempts_used"],
        )

    def test_reentry_reset_cannot_reuse_the_failure_cluster(self) -> None:
        args = _flat_args(dynamic_state=_cycle_two_transition_state())
        reset = _available_reentry_budget()
        reset.update(
            {
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 0,
                "cooldown_until": None,
                "reset_independent_cluster_id": "c-long",
                "reset_previous_regime": "TREND_UP",
                "reset_current_regime": "RANGE",
                "reset_new_tranche_id": "t-long",
                "reset_evidence_refs": ["source:h-short"],
                "status": "RESET",
            }
        )
        args["reentry_budget_state"] = reset
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_REENTRY_RESET_QUALIFICATION_INVALID",
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_qualified_reset_row_opens_only_its_new_absolute_window(self) -> None:
        state = _cycle_two_transition_state()
        args = _flat_args(dynamic_state=state)
        args["reference_context"] = "REENTRY_LONG_RESEARCH_INTENT"
        args["wait_assessment"]["review_deadline"] = "2026-08-07T00:30:00Z"
        args["inactivity_opportunity_watchdog"]["next_watchdog_review_at"] = (
            "2026-08-07T00:30:00Z"
        )
        reenter = args["candidates"][0]
        reenter.update(
            {
                "candidate_id": "reenter-long",
                "action_kind": "REENTER",
                "hypothesis_ids": ["h-zone-long"],
                "cluster_ids": ["c-zone-long"],
                "reentry_obligation_id": "o-prior",
                "new_evidence_refs": ["source:h-short"],
            }
        )
        args["risk_tranches"][0].update(
            {
                "candidate_id": "reenter-long",
                "entry_mode": "RETEST_OR_REENTRY",
                "supporting_cluster_ids": ["c-zone-long"],
                "new_evidence_refs": ["source:h-short"],
            }
        )
        args["reentry_obligations"].append(
            _obligation(
                "o-prior",
                "old-closed-tranche",
                "LONG",
                "h-zone-long",
                "c-zone-long",
                plan_state="CONDITIONAL",
            )
        )
        args["selected_candidate_id"] = "reenter-long"
        args["alternative_candidate_rank"] = ["open-short", "wait"]
        reset = _available_reentry_budget()
        reset.update(
            {
                "rolling_window_started_at": state["as_of"],
                "rolling_window_expires_at": "2026-08-08T00:15:00Z",
                "attempts_used": 0,
                "cumulative_reference_risk": "0",
                "consecutive_failures": 0,
                "cooldown_until": None,
                "reset_independent_cluster_id": "c-zone-long",
                "reset_previous_regime": "TREND_UP",
                "reset_current_regime": "RANGE",
                "reset_new_tranche_id": "t-long",
                "reset_evidence_refs": ["source:h-short"],
                "status": "RESET",
            }
        )
        args["reentry_budget_state"] = reset

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual("RESET", document["reentry_budget_state"]["status"])
        self.assertEqual(
            state["as_of"],
            document["reentry_budget_state"]["rolling_window_started_at"],
        )
        self.assertEqual("reenter-long", document["selected_candidate_id"])

    def test_watchdog_forces_review_and_shadow_comparison_not_entry(self) -> None:
        args = _flat_args()
        args["inactivity_opportunity_watchdog"] = _watchdog(due=True)
        document = build_v32_dynamic_action_plan_v1(**args)
        watchdog = document["inactivity_opportunity_watchdog"]
        self.assertTrue(watchdog["forced_review_due"])
        self.assertFalse(watchdog["forces_action"])

        forced = deepcopy(args)
        forced["inactivity_opportunity_watchdog"]["forces_action"] = True
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_WATCHDOG_FORCED_ENTRY_FORBIDDEN"
        ):
            build_v32_dynamic_action_plan_v1(**forced)

    def test_watchdog_current_pilot_thresholds_are_exact(self) -> None:
        for cycles, seconds in ((4, 7200), (8, 3600), (10, 7200), (8, 10)):
            with self.subTest(cycles=cycles, seconds=seconds):
                args = _flat_args()
                watchdog = args["inactivity_opportunity_watchdog"]
                watchdog["max_wait_cycles_before_review"] = cycles
                watchdog["max_inactivity_seconds"] = seconds
                with self.assertRaisesRegex(
                    V32DynamicActionPlanError,
                    "V32_ACTION_WATCHDOG_(PILOT_THRESHOLD_INVALID|INVALID)",
                ):
                    build_v32_dynamic_action_plan_v1(**args)

    def test_unqualified_latency_remains_unknown_and_cannot_imply_protection(self) -> None:
        args = _flat_args()
        document = build_v32_dynamic_action_plan_v1(**args)
        controls = document["future_execution_hazard"][
            "future_execution_control_requirements"
        ]
        self.assertNotIn("PRE_ACK_VENUE_NATIVE_REDUCE_ONLY_PROTECTION", controls)
        self.assertIn(
            "ATOMIC_ATTACHED_PROTECTION_CAPABILITY_MUST_BE_VENUE_QUALIFIED",
            controls,
        )
        self.assertIn(
            "NO_NEW_ENTRY_IF_ATOMIC_ATTACHED_PROTECTION_IS_UNSUPPORTED_OR_UNQUALIFIED",
            controls,
        )
        self.assertIn(
            "POST_FILL_PRE_PROTECTION_ACK_IS_UNPROTECTED_EXPOSURE_FREEZE_NEW_RISK_AND_ONLY_PREAUTHORIZED_REDUCE_ONLY_CLOSE_OR_RECONCILE",
            controls,
        )
        self.assertIn("NO_FILL_PRICE_OR_FLAT_POSITION_GUARANTEE", controls)

        missing_protection_qualification = deepcopy(args)
        missing_protection_qualification["future_execution_hazard"][
            "future_execution_control_requirements"
        ].remove(
            "ATOMIC_ATTACHED_PROTECTION_CAPABILITY_MUST_BE_VENUE_QUALIFIED"
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_EXECUTION_HAZARD_CONTROLS_INCOMPLETE",
        ):
            build_v32_dynamic_action_plan_v1(**missing_protection_qualification)

        invented_latency = deepcopy(args)
        invented_latency["future_execution_hazard"]["future_latency_bound_ms"] = 750
        invented_latency["future_execution_hazard"]["latency_qualification_status"] = "QUALIFIED"
        invented_latency["future_execution_hazard"]["latency_evidence_refs"] = ["assumption"]
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_LATENCY_BOUND_NOT_QUALIFIED_FOR_CURRENT_PILOT",
        ):
            build_v32_dynamic_action_plan_v1(**invented_latency)

        overclaim = deepcopy(args)
        overclaim["future_execution_hazard"]["current_protection_claim"] = "STOP_PROTECTS_NOW"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_EXECUTION_HAZARD_OVERCLAIM"
        ):
            build_v32_dynamic_action_plan_v1(**overclaim)

        incomplete = deepcopy(args)
        incomplete["future_execution_hazard"]["required_scenarios"].remove(
            "VENUE_UNAVAILABLE"
        )
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_EXECUTION_HAZARD_SCENARIOS_INCOMPLETE",
        ):
            build_v32_dynamic_action_plan_v1(**incomplete)

        no_gap_buffer = deepcopy(args)
        no_gap_buffer["risk_tranches"][0]["tail_gap_reference"] = "0"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_EXECUTION_STRESS_BUFFER_REQUIRED",
        ):
            build_v32_dynamic_action_plan_v1(**no_gap_buffer)

        unbound = deepcopy(args)
        unbound["risk_tranches"][0]["event_risk_guards"].remove("hazard-v1")
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_EXECUTION_HAZARD_NOT_BOUND_TO_TRANCHE",
        ):
            build_v32_dynamic_action_plan_v1(**unbound)

    def test_action_grid_is_complete_for_every_reference_intent(self) -> None:
        self.assertEqual(
            {action for context in (
                "FLAT_RESEARCH_INTENT",
                "LONG_RESEARCH_INTENT",
                "SHORT_RESEARCH_INTENT",
                "REENTRY_LONG_RESEARCH_INTENT",
                "REENTRY_SHORT_RESEARCH_INTENT",
            ) for action, _ in legal_v32_dynamic_action_keys_v1(context)},
            {"OPEN_PROBE", "ADD", "HOLD", "REDUCE", "CLOSE", "REENTER", "REVERSE", "WAIT"},
        )

        long_keys = set(legal_v32_dynamic_action_keys_v1("LONG_RESEARCH_INTENT"))
        self.assertIn(("HOLD", "LONG"), long_keys)
        self.assertNotIn(("WAIT", "NONE"), long_keys)

    def test_hold_is_distinct_from_flat_wait_and_binds_current_intent(self) -> None:
        args = _long_intent_args()
        args["selected_candidate_id"] = "hold-long"
        args["alternative_candidate_rank"] = [
            "add-long",
            "reduce-long",
            "close-long",
            "reverse-short",
        ]
        document = build_v32_dynamic_action_plan_v1(**args)
        selected = next(
            row
            for row in document["candidates"]
            if row["candidate_id"] == "hold-long"
        )
        self.assertEqual("HOLD", selected["action_kind"])
        self.assertEqual("LONG", selected["direction"])
        self.assertEqual("prior-long-tranche", selected["parent_tranche_id"])

        conflated = deepcopy(args)
        selected = next(
            row
            for row in conflated["candidates"]
            if row["candidate_id"] == "hold-long"
        )
        selected["action_kind"] = "WAIT"
        selected["direction"] = "NONE"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError,
            "V32_ACTION_WAIT_CANDIDATE_INVALID|V32_ACTION_LEGAL_GRID_INCOMPLETE",
        ):
            build_v32_dynamic_action_plan_v1(**conflated)

        args = _flat_args()
        args["candidates"].pop()
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_LEGAL_GRID_INCOMPLETE"
        ):
            build_v32_dynamic_action_plan_v1(**args)

    def test_multiple_independent_same_direction_plans_are_allowed_and_budgeted(self) -> None:
        args = _flat_args()
        args["candidates"].append(
            _candidate(
                "open-long-zone",
                "OPEN_PROBE",
                "LONG",
                hypothesis_ids=["h-zone-long"],
                cluster_ids=["c-zone-long"],
                risk_tranche_id="t-long-zone",
            )
        )
        args["risk_tranches"].append(
            _tranche(
                "t-long-zone",
                "open-long-zone",
                "LONG",
                "c-zone-long",
                "o-long-zone",
            )
        )
        args["reentry_obligations"].append(
            _obligation(
                "o-long-zone",
                "t-long-zone",
                "LONG",
                "h-zone-long",
                "c-zone-long",
            )
        )
        args["alternative_candidate_rank"] = [
            "open-long-zone",
            "open-short",
            "wait",
        ]

        document = build_v32_dynamic_action_plan_v1(**args)

        self.assertEqual(
            sum(
                Decimal(row["reference_risk"])
                for row in document["cluster_risk_allocations"]
            ),
            Decimal("1.0"),
        )
        self.assertEqual(
            document["directional_subjective_tier_cap_units"],
            {"LONG": 100, "SHORT": 50},
        )
        self.assertEqual(
            len(
                [
                    row
                    for row in document["candidates"]
                    if (row["action_kind"], row["direction"])
                    == ("OPEN_PROBE", "LONG")
                ]
            ),
            2,
        )

    def test_nominal_or_account_fields_are_rejected_by_exact_contract(self) -> None:
        args = _flat_args()
        args["candidates"][0]["notional_pct"] = "5"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_CANDIDATE_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**args)

        market_money = _flat_args()
        market_money["risk_tranches"][0]["trailing_plan"][
            "floating_gain_is_market_money"
        ] = True
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_TRAILING_SAFETY_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**market_money)

        fixed_trail = _flat_args()
        fixed_trail["risk_tranches"][0]["trailing_plan"]["mode"] = "FIXED_3_8_15"
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_TRAILING_MODE_INVALID"
        ):
            build_v32_dynamic_action_plan_v1(**fixed_trail)

    def test_recomputed_digest_cannot_hide_claim_or_scaled_budget_drift(self) -> None:
        args = _flat_args()
        document = build_v32_dynamic_action_plan_v1(**args)

        claim_drift = deepcopy(document)
        claim_drift["market_money_claim"] = "FLOATING_GAIN_IS_FREE_CAPITAL"
        claim_drift = self_digest(claim_drift, "dynamic_action_plan_digest")
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_dynamic_action_plan_v1(
                claim_drift, dynamic_research_state=args["dynamic_research_state"]
            )

        budget_drift = deepcopy(document)
        budget_drift["distributable_reference_risk_budget"] = "1.1"
        budget_drift = self_digest(budget_drift, "dynamic_action_plan_digest")
        with self.assertRaisesRegex(
            V32DynamicActionPlanError, "V32_ACTION_RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_dynamic_action_plan_v1(
                budget_drift, dynamic_research_state=args["dynamic_research_state"]
            )


if __name__ == "__main__":
    unittest.main()
