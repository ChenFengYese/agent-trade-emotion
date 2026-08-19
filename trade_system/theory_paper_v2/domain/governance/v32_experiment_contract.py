"""Frozen-shape V3.2 dynamic-aggressive process-pilot contract.

The builder defines the intended 16-cycle, 15-minute, public-data-only pilot.
It binds prerequisite semantic documents but grants no authority and performs
no source, Agent, monitor, portfolio, or execution work.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..contracts.canonical import self_digest, verify_self_digest


class V32ExperimentContractError(ValueError):
    """The V3.2 pilot contract drifted or crossed its authority boundary."""


SCHEMA_ID = "theory_paper_v32_dynamic_aggressive_process_pilot_contract_v1"
SCHEMA_VERSION = "1.0.0"
DIGEST_FIELD = "v32_experiment_contract_digest"
THEORY_VERSION = "3.2.1"
PILOT_NAME = "V32_DYNAMIC_AGGRESSIVE_BTCUSDT_15M_PROCESS_PILOT"

TOTAL_ANALYSIS_CYCLES = 16
OUTCOME_HORIZONS_SECONDS = (900, 3600, 14400)
TOTAL_OUTCOME_SCHEDULES = TOTAL_ANALYSIS_CYCLES * len(OUTCOME_HORIZONS_SECONDS)
ANALYSIS_INTERVAL_SECONDS = 900
INACTIVITY_REVIEW_CYCLES = 8
INACTIVITY_REVIEW_SECONDS = INACTIVITY_REVIEW_CYCLES * ANALYSIS_INTERVAL_SECONDS
REENTRY_ROLLING_WINDOW_SECONDS = 86400
MIN_MARKET_EFFICACY_DECISIONS = 240

SUPPORT_BINDING_KEYS = (
    "association_preregistration_digest",
    "authorized_revision_support_bundle_digest",
    "clock_policy_digest",
    "evaluation_contract_digest",
    "outcome_adapter_contract_digest",
    "recovery_supervision_policy_digest",
    "twelve_axis_source_registry_digest",
    "workspace_freeze_receipt_digest",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "contract_id",
        "run_id",
        "frozen_at",
        "pilot_name",
        "theory_binding",
        "support_bindings",
        "instrument",
        "pilot_protocol",
        "authorized_revision_policy",
        "hypothesis_policy",
        "zone_and_modifier_policy",
        "risk_policy",
        "action_policy",
        "timeframe_policy",
        "outcome_policy",
        "inactivity_policy",
        "evaluation_policy",
        "stop_policy",
        "authority_boundary",
        "readiness_status",
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32ExperimentContractError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32ExperimentContractError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32ExperimentContractError(code) from exc
    if parsed.tzinfo is None:
        raise V32ExperimentContractError(code)
    canonical = parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if canonical != text:
        raise V32ExperimentContractError(code)
    return text


def _relative_ref(value: Any, code: str) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise V32ExperimentContractError(code)
    return text


def _support_bindings(value: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(value, Mapping) or tuple(sorted(value)) != tuple(
        sorted(SUPPORT_BINDING_KEYS)
    ):
        raise V32ExperimentContractError("V32_EXPERIMENT_SUPPORT_BINDINGS_INVALID")
    return {
        key: _digest(
            value[key], f"V32_EXPERIMENT_SUPPORT_BINDING_INVALID:{key}"
        )
        for key in SUPPORT_BINDING_KEYS
    }


def _authority_boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "credential_use": False,
        "funds_access": False,
        "portfolio_mutation": False,
        "fill_claim": False,
        "pnl_claim": False,
    }


def build_v32_experiment_contract_v1(
    *,
    contract_id: str,
    run_id: str,
    frozen_at: str,
    theory_relative_ref: str,
    theory_physical_sha256: str,
    theory_semantic_digest: str,
    support_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the exact process-pilot contract without granting run authority."""

    document = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "contract_id": _text(contract_id, "V32_EXPERIMENT_CONTRACT_ID_INVALID"),
        "run_id": _text(run_id, "V32_EXPERIMENT_RUN_ID_INVALID"),
        "frozen_at": _time(frozen_at, "V32_EXPERIMENT_FROZEN_AT_INVALID"),
        "pilot_name": PILOT_NAME,
        "theory_binding": {
            "relative_ref": _relative_ref(
                theory_relative_ref, "V32_EXPERIMENT_THEORY_REF_INVALID"
            ),
            "theory_version": THEORY_VERSION,
            "physical_sha256": _digest(
                theory_physical_sha256,
                "V32_EXPERIMENT_THEORY_PHYSICAL_DIGEST_INVALID",
            ),
            "semantic_digest": _digest(
                theory_semantic_digest,
                "V32_EXPERIMENT_THEORY_SEMANTIC_DIGEST_INVALID",
            ),
            "full_utf8_document_required_in_agent_context": True,
        },
        "support_bindings": _support_bindings(support_bindings),
        "instrument": {
            "venue": "OKX",
            "instrument_id": "BTC-USDT-SWAP",
            "market_type": "PERPETUAL_SWAP",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "spot_claim": False,
        },
        "pilot_protocol": {
            "analysis_cycles": TOTAL_ANALYSIS_CYCLES,
            "analysis_interval_seconds": ANALYSIS_INTERVAL_SECONDS,
            "cycle_1_mode": "FULL_CONTEXT",
            "cycle_2_to_16_mode": "DELTA_UPDATE",
            "closed_bar_only": True,
            "one_proposal_and_one_selection_attempt_per_cycle": True,
            "outcome_horizons_seconds": list(OUTCOME_HORIZONS_SECONDS),
            "scheduled_outcomes": TOTAL_OUTCOME_SCHEDULES,
            "outcome_only_tail_required": True,
            "mid_run_rule_change_forbidden": True,
            "old_run_or_qualification_samples_counted": False,
        },
        "authorized_revision_policy": {
            "support_bundle_digest_key": (
                "authorized_revision_support_bundle_digest"
            ),
            "recovery_supervision_policy_digest_key": (
                "recovery_supervision_policy_digest"
            ),
            "workspace_freeze_receipt_digest_key": (
                "workspace_freeze_receipt_digest"
            ),
            "original_context_documents": "WRITE_ONCE_FULL_REPLAY_REQUIRED",
            "context_capacity_order": [
                "DETERMINISTIC_DEDUPLICATION",
                "TYPED_COMPACTION",
                "DEPENDENCY_CLOSURE_SHARDING",
                "ALL_NECESSARY_SHARDS",
            ],
            "arbitrary_top_k_or_semantic_omission_forbidden": True,
            "context_capacity_unresolved_only_after_all_safe_paths": True,
            "objective_unknown_preserved": True,
            "subjective_unknown_assessment_requires_current_pit_evidence": True,
            "subjective_unknown_assessment_is_probability": False,
            "manual_public_evidence_is_future_only_no_backfill": True,
            "environment_localization_must_be_declared": True,
            "core_theory_evaluation_timing_and_authority_may_be_localized": False,
            "authorized_revision_cycle_registry_required": True,
            "cycle_audit_narrative_stage": (
                "POST_CORRESPONDING_TYPED_BOUNDARY"
            ),
            "acceptance_narrative_stage": "POST_ACCEPTANCE_ONLY",
            "cycle_audit_completion_required_before_next_cycle_permit": True,
            "supervisor_role": "READ_ONLY_ADVISORY_SINGLE_STRATEGY_AGENT_OWNER",
        },
        "hypothesis_policy": {
            "required_types": [
                "STATE",
                "ATTRIBUTION",
                "FORECAST_PATH",
                "ACTION_THESIS",
            ],
            "directional_opposition": (
                "CANDIDATE_COMPLETENESS_ONLY_EXTREME_UNCERTAINTY_OR_BLOCKED_ALLOWED"
            ),
            "residuals": "EXACTLY_ONE_OTHER_AND_ONE_UNKNOWN",
            "subjective_plausibility_tiers": [
                "EXTREME_UNCERTAINTY",
                "LOW",
                "HIGH",
            ],
            "subjective_tier_is_probability": False,
            "subjective_tier_enters_brier_ece_ev_or_kelly": False,
            "tier_transition_policy": (
                "ANY_CHANGE_REQUIRES_NEW_PIT_NO_DIRECT_EXTREME_TO_HIGH_"
                "OR_HIGH_TO_EXTREME_TERMINAL_IS_EXTREME_ZERO_RISK"
            ),
            "ttl_seconds_by_type": {
                "STATE": 14400,
                "ATTRIBUTION": 86400,
                "FORECAST_PATH": 14400,
                "ACTION_THESIS": 3600,
            },
            "expiry_action": "EXPIRE_AND_CANCEL_DEPENDENT_UNTRIGGERED_PLANS",
            "renewal_policy": (
                "NEW_REVISION_OLD_DIGEST_OLD_EXPIRY_NEW_EVIDENCE_AND_REGIME_RECHECK"
            ),
            "timestamp_only_renewal_forbidden": True,
            "fixed_fifty_percent_decay_is_unselected_comparison_arm": True,
        },
        "zone_and_modifier_policy": {
            "zone_path_roles": [
                "ZONE_REJECTION",
                "ZONE_ABSORPTION_BREAK",
                "FALSE_BREAK_REVERSION",
                "ZONE_NO_EFFECT_OTHER",
            ],
            "modifier_types": [
                "FALSE_BREAK_STOP_RUN",
                "LIQUIDITY_VACUUM",
                "FORCED_LIQUIDATION_CASCADE",
                "CROSS_VENUE_DISLOCATION",
                "VENUE_OR_NETWORK_DISRUPTION",
                "EVENT_SHOCK",
                "ATTENTION_MOMENTUM_FEEDBACK",
                "OTHER",
                "UNKNOWN",
            ],
            "actor_identity_from_candles_or_volume_forbidden": True,
            "modifier_global_broadcast_forbidden": True,
            "modifier_effect_cap_units": {
                "SUPPORTS_PATH": 100,
                "MODULATES_PATH": 50,
                "OPPOSES_PATH": 50,
                "INVALIDATES_PATH": 0,
                "UNKNOWN_STATUS": 50,
            },
            "shared_zone_or_dependency_required": True,
            "post_outcome_zone_movement_forbidden": True,
        },
        "risk_policy": {
            "mode": (
                "FIXED_ONE_USDT_STRESS_REFERENCE_NO_ACCOUNT_OR_EXECUTION_CLAIM"
            ),
            "reference_risk_unit": "NON_ACCOUNT_RESEARCH_STRESS_USDT",
            "reference_risk_upper_bound": "1",
            "raw_reference_envelope_policy": (
                "FIXED_ONE_USDT_STRESS_REFERENCE_NO_ACCOUNT_OR_EXECUTION_"
                "CLAIM_NO_AGENT_OVERRIDE"
            ),
            "future_portfolio_adapter_policy": (
                "SEPARATELY_AUTHORIZED_OBJECTIVE_ACCOUNT_RISK_ADAPTER_ONLY"
            ),
            "effective_budget_method": (
                "FIXED_ENVELOPE_TIMES_MIN_SUBJECTIVE_TIER_AND_RESIDUAL_"
                "THEN_PATH_NON_INFLATION_CAP_AFTER_TYPED_HARD_GATES"
            ),
            "subjective_tier_risk_cap_units": {
                "EXTREME_UNCERTAINTY": 0,
                "LOW": 50,
                "HIGH": 100,
            },
            "subjective_tier_cap_policy": (
                "CAP_ONLY_HIGH_NEVER_AMPLIFIES_OBJECTIVE_CAP"
            ),
            "same_direction_support_formula": "MAX_CLUSTER_TIER_NEVER_SUM",
            "opposed_direction_support_combination": "MAX_TIER_NEVER_SUM",
            "hypothesis_evidence_chain_coverage_policy": (
                "DETERMINISTIC_COMPLETE_OR_INCOMPLETE_DIAGNOSTIC_ONLY_"
                "NO_RISK_SCALAR"
            ),
            "source_admission_coverage_status": "UNKNOWN_NOT_IN_DYNAMIC_STATE",
            "residual_uncertainty_cap": (
                "ONE_MINUS_MAX_OTHER_OR_UNKNOWN_TIER_CAP"
            ),
            "objective_quality_policy": (
                "REPLAYABLE_DIAGNOSTICS_AND_TYPED_HARD_FEASIBILITY_GATES_"
                "NO_COVERAGE_REGIME_LIQUIDITY_GEOMETRY_OR_COST_SCALAR"
            ),
            "objective_reference_risk_input_policy": {
                "datum_container": (
                    "support_documents.agent_market_graph_view."
                    "current_non_bar_datums"
                ),
                "contract_value_datum_id": "contract-value",
                "contract_value_metric_kind": "INSTRUMENT_CTVAL",
                "contract_value_unit": "BTC_PER_CONTRACT",
                "contract_multiplier_datum_id": "contract-multiplier",
                "contract_multiplier_metric_kind": "INSTRUMENT_CTMULT",
                "contract_multiplier_unit": "OKX_CT_MULT",
                "multiplier_reference_derivation": (
                    "CONTRACT_VALUE_TIMES_CONTRACT_MULTIPLIER"
                ),
                "multiplier_reference_unit": "BTC_PER_CONTRACT",
                "price_tick_datum_id": "price-tick",
                "price_tick_metric_kind": "INSTRUMENT_TICKSZ",
                "price_tick_unit": "USDT_PER_BTC",
                "quantity_step_datum_id": "quantity-step",
                "quantity_step_metric_kind": "INSTRUMENT_LOTSZ",
                "quantity_step_unit": "CONTRACTS",
                "reference_scale_quantum_derivation": "QUANTITY_STEP",
                "minimum_quantity_datum_id": "minimum-quantity",
                "minimum_quantity_metric_kind": "INSTRUMENT_MINSZ",
                "minimum_quantity_unit": "CONTRACTS",
                "derived_reference_scale_unit": "CONTRACTS",
                "derived_reference_scale_minimum_policy": (
                    "GREATER_THAN_OR_EQUAL_TO_OBSERVED_MINIMUM_QUANTITY"
                ),
                "price_tick_alignment_fields": [
                    "conditional_entry_reference",
                    "protective_stop_reference",
                    "previous_stop_reference_WHEN_PRESENT",
                    "parent_entry_reference_WHEN_PRESENT",
                    "minimum_noise_execution_buffer",
                    "take_profit_targets[*].reference_price",
                ],
                "positive_risk_requires_observed_qualified_contract_specs": True,
                "agent_override_forbidden": True,
                "frozen_non_account_research_stress_policy": {
                    "policy_label": (
                        "FROZEN_NON_ACCOUNT_RESEARCH_STRESS_NOT_ACTUAL_FEE_"
                        "OR_FILL_OR_MAX_LOSS"
                    ),
                    "stress_reference_unit": "USDT_PER_CONTRACT",
                    "conditional_entry_reference_unit": "USDT_PER_BTC",
                    "notional_per_contract_derivation": (
                        "CONTRACT_EXPOSURE_TIMES_CONDITIONAL_ENTRY_REFERENCE"
                    ),
                    "stress_reference_derivation": (
                        "CONTRACT_EXPOSURE_TIMES_CONDITIONAL_ENTRY_REFERENCE_"
                        "TIMES_FROZEN_RATE"
                    ),
                    "rate_source_basis": (
                        "PREREGISTERED_CONSERVATIVE_NON_ACCOUNT_RESEARCH_"
                        "COMPARATOR_ASSUMPTIONS_NOT_ACCOUNT_OR_FILL_CALIBRATION"
                    ),
                    "rates": {
                        "fee_stress_reference": "0.002",
                        "slippage_stress_reference": "0.001",
                        "funding_bound_reference": "0.001",
                        "tail_gap_reference": "0.005",
                    },
                    "unknown_retention": {
                        "actual_account_fee_tier": "UNKNOWN_NOT_ACCESSED",
                        "actual_slippage": "UNKNOWN_NOT_OBSERVED",
                        "actual_tail_max_loss": "UNKNOWN_NOT_DEFINED",
                    },
                    "future_account_or_execution_adapter_policy": (
                        "SEPARATE_AUTHORIZATION_AND_QUALIFICATION_REQUIRED"
                    ),
                },
                "dimensional_scale_policy": (
                    "NON_ACCOUNT_RESEARCH_STRESS_USDT_DIVIDED_BY_"
                    "USDT_PER_CONTRACT_EQUALS_CONTRACTS"
                ),
            },
            "high_tier_evidence_policy": (
                "INITIAL_HIGH_OR_LOW_TO_HIGH_REQUIRES_TWO_FRESH_MECHANISM_"
                "DISTINCT_REFS_AND_DIRECTIONAL_COUNTER_EVIDENCE"
            ),
            "mechanism_distinct_evidence_policy": (
                "PRESERVE_FULL_CLOSURE_IGNORE_ONLY_SHARED_VENUE_PROJECTION_"
                "FOR_PAIRING_REQUIRE_DISJOINT_OTHER_MATERIAL_DEPENDENCIES_"
                "DIFFERENT_REQUEST_AND_DIRECTIONAL_OBSERVABLE_FAMILY_"
                "NOT_STATISTICAL_INDEPENDENCE"
            ),
            "directional_observable_families": [
                "PRICE_ACTION",
                "POSITIONING",
                "FUNDING_CROWDING",
                "ORDERBOOK_LIQUIDITY",
                "TRADE_FLOW",
            ],
            "price_action_components": [
                "TICKER",
                "MARK_PRICE",
                "CLOSED_CANDLES_15M",
                "CLOSED_CANDLES_1H",
                "CLOSED_CANDLES_4H",
                "CLOSED_CANDLES_1D",
            ],
            "nondirectional_metadata_families": [
                "PROVIDER_METADATA",
                "CONTRACT_SPEC",
            ],
            "regime_transition_policy": (
                "ENTER_NONDIRECTIONAL_ONE_FRESH_HARD_REF_ALLOWED_"
                "NONDIRECTIONAL_TO_DIRECTION_REQUIRES_TWO_FRESH_MECHANISM_"
                "DISTINCT_REFS_"
                "OR_TWO_CONSECUTIVE_MACHINE_VERIFIED_CLOSED_15M_BARS"
            ),
            "agent_authored_numeric_quality_forbidden": True,
            "relative_allocation": (
                "DISCRETE_CLUSTER_UNITS_EXTREME_ZERO_LOW_ONE_HIGH_TWO"
            ),
            "dependency_cluster_aggregation": (
                "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM"
            ),
            "minimum_forced_risk": "0",
            "unknown_fact_integrity_blocks_dependent_risk": True,
            "unknown_research_reference_loss_bound_blocks_new_risk": True,
            "unknown_real_execution_max_loss_blocks_future_execution": True,
            "loss_averaging_forbidden": True,
            "unlocked_paper_profit_as_free_budget_forbidden": True,
        },
        "action_policy": {
            "legal_research_actions": [
                "OPEN_PROBE",
                "ADD",
                "HOLD",
                "REDUCE",
                "CLOSE",
                "REENTER",
                "REVERSE",
                "WAIT",
            ],
            "future_physical_escape_contract": {
                "owner": (
                    "INDEPENDENT_EXECUTION_RISK_CAPSULE_NOT_STRATEGY_AGENT_"
                    "OR_RESEARCH_RECOVERY_SUPERVISOR"
                ),
                "implementation_status": "NOT_IMPLEMENTED_NOT_QUALIFIED",
                "separate_authority_required": True,
                "research_recovery_supervisor_is_execution_risk_supervisor": False,
                "activation_gates": [
                    "SEPARATE_ACCOUNT_ORDER_CREDENTIAL_AND_FUNDS_AUTHORITY",
                    "VENUE_ATOMIC_PROTECTION_CAPABILITY_QUALIFIED",
                    "POSITION_ORDER_FILL_ACK_AND_PROTECTION_TRUTH_STATE_MACHINE_QUALIFIED",
                    "IDEMPOTENT_REDUCE_ONLY_AND_MARKET_FALLBACK_ROUTE_QUALIFIED",
                    "PARTIAL_FILL_OVER_CLOSE_DEDUP_TIMEOUT_AND_RECONCILIATION_TRANSITIONS_QUALIFIED",
                    "TRANSPORT_REDUNDANCY_OR_EXPLICIT_DEGRADED_MODE_QUALIFIED",
                    "EXTERNAL_ALERT_AND_HUMAN_ACK_CHANNEL_QUALIFIED",
                    "LATENCY_PARTITION_AND_VENUE_OUTAGE_CHAOS_TESTS_QUALIFIED",
                ],
                "current_pilot_order_capability": False,
                "current_pilot_scope": "PUBLIC_LOCAL_NON_EXECUTABLE",
                "current_latency_bound_ms": None,
                "current_latency_qualification_status": "UNKNOWN_NOT_QUALIFIED",
                "entry_protection_mode": (
                    "ATOMIC_ATTACHED_PROTECTION_IN_SAME_ENTRY_REQUEST_AND_"
                    "INDEPENDENT_FINAL_CONFIRMATION"
                ),
                "unsupported_atomic_attachment_response": "BLOCK_NEW_ENTRY",
                "zero_position_pre_ack_reduce_only_assumption_forbidden": True,
                "post_fill_pre_protection_confirmation_state": (
                    "UNPROTECTED_EXPOSURE_FREEZE_NEW_RISK_AND_PREAUTHORIZED_"
                    "REDUCE_ONLY_CLOSE_THEN_RECONCILE"
                ),
                "anomaly_response": "FREEZE_ALL_NEW_RISK",
                "fallback_sequence": (
                    "IDEMPOTENT_REDUCE_ONLY_IOC_OR_MARKETABLE_THEN_MARKET_"
                    "ONLY_WITH_SEPARATE_FUTURE_AUTHORIZATION"
                ),
                "terminal_truth": "FINAL_POSITION_RECONCILIATION_REQUIRED",
                "venue_unavailable_response": (
                    "UNRESOLVED_EXPOSURE_ALERT_AND_HUMAN_ESCALATION"
                ),
                "guaranteed_exit_price": False,
                "guaranteed_flat_position": False,
            },
            "direction_policy": (
                "OPEN_PROBE_ADD_REENTER_REVERSE_REQUIRE_LONG_OR_SHORT_"
                "HOLD_REDUCE_CLOSE_REFER_TO_CURRENT_INTENT_WAIT_REQUIRES_NONE"
            ),
            "partial_harvest_is_management_event_not_independent_action": True,
            "hold_is_distinct_from_flat_wait": True,
            "entry_modes": [
                "ANTICIPATORY_PROBE",
                "REACTION_ENTRY",
                "BREAK_ACCELERATION",
                "RETEST_OR_REENTRY",
            ],
            "plan_states": [
                "PLANNED",
                "CONDITIONAL",
                "CANCELLED",
                "EXPIRED",
                "SUPERSEDED",
            ],
            "wait_is_costless_default": False,
            "wait_requires_probe_dominance_or_hard_block": True,
            "selection_is_non_executable_research_plan": True,
            "false_break_reentry_requires_new_tranche": True,
            "market_regime_states": [
                "TREND_UP",
                "TREND_DOWN",
                "NEUTRAL",
                "RANGE",
                "CHOPPY",
                "VOLATILITY_WITHOUT_DIRECTION",
                "TRANSITION",
                "OTHER",
                "UNKNOWN",
            ],
            "nondirectional_regime_policy": (
                "NEUTRAL_CHOPPY_VOLATILITY_WITHOUT_DIRECTION_TRANSITION_"
                "OTHER_UNKNOWN_"
                "BLOCK_DIRECTIONAL_NEW_RISK_ZERO_CURRENT_BUDGET_"
                "RISK_CANDIDATES_REMAIN_UNTRIGGERED_CONDITIONAL_PLANS_"
                "BOUND_ONLY_TO_TYPED_BREAKOUT_BOUNDARIES_"
                "NO_ORDER_SUBMISSION_RANGE_MAY_RETAIN_CONDITIONAL_"
                "MEAN_REVERSION_PATHS"
            ),
            "nondirectional_research_breakout_trigger_policy": {
                "derivation_owner": "DOMAIN_FROM_SEALED_CANDIDATES_AND_ZONES",
                "agent_supplied_threshold_or_comparator_allowed": False,
                "source_component_id": "CLOSED_CANDLES_15M",
                "timeframe": "15M",
                "observed_field": "close",
                "closed_bar_required": True,
                "required_consecutive_closed_bars_for_reanalysis": 1,
                "direction_transition_gate_unchanged": (
                    "TWO_FRESH_MECHANISM_DISTINCT_REFS_OR_TWO_CONSECUTIVE_"
                    "MACHINE_VERIFIED_CLOSED_15M_BARS"
                ),
                "long_leg_binding": "ZONE_UPPER_BOUND_STRICT_GT",
                "short_leg_binding": "ZONE_LOWER_BOUND_STRICT_LT",
                "candidate_zone_count_per_direction": 1,
                "resolution_policy": (
                    "FIRST_MATCH_RETIRES_PAIR_AND_REQUIRES_FRESH_REANALYSIS"
                ),
                "match_effect": (
                    "RESEARCH_REANALYSIS_ONLY_NO_AUTOMATIC_ACTION_OR_RISK"
                ),
                "continuous_monitor_implemented": False,
                "order_or_oco_claim": "NONE",
                "executable": False,
            },
            "reference_tranche_lineage_policy": {
                "scope": "SOLE_RESEARCH_INTENT_PARENT_NOT_POSITION_OR_FILL",
                "genesis_active_parent_allowed": False,
                "risk_plan_promotes_exact_selected_tranche": True,
                "hold_or_reduce_carries_exact_parent": True,
                "close_retires_parent": True,
                "add_parent_id_direction_entry_and_stop_exact_echo_required": True,
                "new_add_or_reverse_tranche_id_must_differ_from_parent": True,
                "parent_support_is_exact_actionable_same_direction_cluster_closure": True,
                "parent_valid_until_is_minimum_of_plan_candidate_and_time_stop": True,
                "expired_parent_must_retire_before_next_plan": True,
                "failure_refs_must_be_fresh_typed_contradiction_or_active_invalidation": True,
                "generic_source_support_renewal_tier_or_zone_ref_cannot_prove_failure": True,
                "failure_cluster_must_be_in_parent_support": True,
                "agent_parent_rotation_or_geometry_rewrite_allowed": False,
            },
            "reentry_budget_policy": {
                "scope": "ONE_GLOBAL_CHURN_BREAKER_PER_INSTRUMENT",
                "rolling_utc_window_required": True,
                "rolling_window_seconds": REENTRY_ROLLING_WINDOW_SECONDS,
                "max_attempts": 2,
                "max_cumulative_reference_risk": "2",
                "max_cumulative_reference_risk_unit": (
                    "NON_ACCOUNT_RESEARCH_STRESS_USDT"
                ),
                "current_pilot_budget_policy": (
                    "FIXED_ONE_NON_ACCOUNT_RESEARCH_STRESS_USDT_PER_COUNTED_"
                    "ATTEMPT_ENVELOPE_TWO_ATTEMPT_CUMULATIVE_CAP_NO_AGENT_"
                    "OVERRIDE"
                ),
                "initial_inactive_open_probe_counts": False,
                "initial_probe_arms_single_use_lock": True,
                "initial_probe_lock_status": "INITIAL_PROBE_USED",
                "initial_probe_lock_window_seconds": (
                    REENTRY_ROLLING_WINDOW_SECONDS
                ),
                "second_unfailed_initial_probe_cannot_be_free": True,
                "initial_probe_lock_allows_counted_open_or_reverse": True,
                "initial_probe_lock_counted_attempts_and_risk_are_durable": True,
                "initial_stop_counts_toward_consecutive_failure_breaker": True,
                "max_consecutive_stop_failures": 2,
                "active_ledger_counted_action_kinds": [
                    "OPEN_PROBE",
                    "REENTER",
                    "REVERSE",
                ],
                "active_ledger_direction_scope": (
                    "ANY_DIRECTION_SAME_INSTRUMENT"
                ),
                "current_pilot_attempt_basis": (
                    "PREVIOUS_ACCEPTED_SELECTED_ELIGIBLE_POSITIVE_RISK_"
                    "ACTIVE_LEDGER_OPEN_PROBE_REENTER_OR_REVERSE_RESEARCH_"
                    "TRANCHE_NOT_FILL_OR_POSITION"
                ),
                "canonical_same_direction_action_kind": "REENTER",
                "attempt_and_cumulative_transition": (
                    "NEXT_ATTEMPTS_EQUALS_PREVIOUS_PLUS_ONE_AND_NEXT_"
                    "CUMULATIVE_EQUALS_PREVIOUS_PLUS_PREVIOUS_SELECTED_"
                    "REFERENCE_RISK_ELSE_BOTH_UNCHANGED"
                ),
                "consecutive_failure_transition": (
                    "INITIAL_STOP_STARTS_AT_ONE_THEN_PLUS_ONE_MAX_ONLY_AFTER_"
                    "COUNTED_ACTIVE_LEDGER_INSTRUMENT_CHURN_ACTION_OPEN_PROBE_"
                    "REENTER_OR_REVERSE_AND_FRESH_CURRENT_PIT_FAILURE_REF_"
                    "ELSE_UNCHANGED"
                ),
                "initial_exit_available_counters": {
                    "attempts_used": 0,
                    "consecutive_failures": 1,
                    "cumulative_reference_risk": "0",
                },
                "cumulative_reference_risk_cap_required": True,
                "two_failures_or_budget_exhaustion_blocks_reentry": True,
                "exhausted_remains_locked_after_cooldown_expiry": True,
                "budget_exhaustion_cooldown_equals_window_expiry": True,
                "cooldown_may_not_be_shortened": True,
                "reset_before_original_window_expiry_forbidden": True,
                "cross_cluster_regime_or_id_change_does_not_clear_window": True,
                "same_direction_risk_aliases_require_normalization": [
                    "OPEN_PROBE",
                    "REVERSE",
                ],
                "opposite_direction_aliases_are_not_free": True,
                "reset_requires": [
                    "NEW_INDEPENDENT_CLUSTER",
                    "MARKET_REGIME_TRANSITION",
                    "NEW_TRANCHE",
                ],
                "obligation_forces_entry": False,
            },
        },
        "timeframe_policy": {
            "roles": ["STRATEGIC_CONTEXT", "TACTICAL_DELTA", "TRIGGER"],
            "strategic_carry_requires_unexpired_and_uninvalidated": True,
            "tactical_and_trigger_refresh_each_delta": True,
            "target_delta_processing_seconds": 120,
            "higher_timeframe_is_prior_not_absolute_direction_ban": True,
            "rsi_arms": [
                "NO_RSI",
                "RSI_TRIGGER_ONLY",
                "RSI_FILTER_ONLY",
                "RSI_PLUS_STRUCTURE",
                "RSI_PLUS_STRUCTURE_AND_FLOW",
            ],
            "rsi_alone_may_increase_risk_budget": False,
        },
        "outcome_policy": {
            "analysis_clock_independent_of_outcome_clock": True,
            "one_public_observation_tick_may_resolve_multiple_due_schedules": True,
            "outcome_grace_seconds": 900,
            "observable": "metric:okx-public-mark-price-usdt",
            "observation_semantics": (
                "FIRST_SHARED_PUBLIC_MARK_TICK_AT_OR_AFTER_HORIZON_WITHIN_GRACE"
            ),
            "attempts_per_tick": 1,
            "raw_transport_persisted_before_parse": True,
            "future_outcome_read_forbidden": True,
            "not_due_blocks_new_analysis": False,
            "coverage_loss_terminal_value": "UNKNOWN_COVERAGE_LOSS",
            "coverage_loss_retry_allowed": False,
            "integrity_failure": "FAILED_CLOSED",
            "stop_or_limit_touched_is_fill": False,
            "position_or_pnl_output_forbidden": True,
        },
        "inactivity_policy": {
            "review_after_consecutive_cycles": INACTIVITY_REVIEW_CYCLES,
            "review_after_seconds": INACTIVITY_REVIEW_SECONDS,
            "current_pilot_thresholds_agent_override_forbidden": True,
            "qualifying_states": ["NO_ELIGIBLE_PROBE", "NO_PLAN_CHANGE"],
            "review_outputs": [
                "REGIME_RECHECK",
                "THRESHOLD_AND_TTL_DIAGNOSIS",
                "DATA_COVERAGE_DIAGNOSIS",
                "SHADOW_BASELINE_COMPARISON",
                "FUTURE_ONLY_METHOD_CANDIDATE",
            ],
            "forced_trade_or_minimum_exposure": False,
            "cash_or_inflation_cost_numeric_without_frozen_benchmark": False,
        },
        "evaluation_policy": {
            "primary_claim": "PROCESS_RELIABILITY_ONLY",
            "shadow_baselines": [
                "V32_SELECTED_PLAN",
                "V31_CONSERVATIVE_WAIT_BIASED_REFERENCE",
                "WAIT_ONLY",
                "SIMPLE_15M_TREND",
                "NO_RSI_REFERENCE",
                "ALWAYS_LONG_PUBLIC_MARK_REFERENCE",
            ],
            "shadow_baseline_replay_policy": (
                "POLICY_ID_VERSION_DIGEST_EXACT_PIT_INPUT_OUTPUT_RECEIPT_"
                "OR_UNKNOWN_NOT_COMPUTED_NO_CALLER_LABEL_SUBSTITUTION"
            ),
            "terminal_mark_path_claim_policy": (
                "DIRECTION_ONLY_PATH_MFE_MAE_AND_OPPORTUNITY_COST_UNKNOWN_"
                "WITHOUT_INTRAHORIZON_PATH_CONTRACT"
            ),
            "process_endpoints": [
                "SIXTEEN_ACCEPTED_ANALYSIS_CYCLES",
                "FORTY_EIGHT_TERMINAL_OUTCOME_SCHEDULES",
                "NO_FUTURE_LEAKAGE",
                "DURABLE_SINGLE_ATTEMPT_AGENT_AND_OUTCOME_CHAINS",
                "DYNAMIC_HYPOTHESIS_ACTION_AND_REENTRY_COVERAGE",
            ],
            "excluded_claims": [
                "PROFITABILITY",
                "CALIBRATED_PROBABILITY",
                "BRIER_ECE_EV_OR_KELLY",
                "REAL_FILL_SLIPPAGE_FUNDING_OR_PNL",
                "AGENT_SUPERIORITY",
                "CAUSALITY",
                "CROSS_REGIME_GENERALIZATION",
            ],
            "minimum_future_decisions_before_market_efficacy_phase": (
                MIN_MARKET_EFFICACY_DECISIONS
            ),
        },
        "stop_policy": {
            "fail_closed_on": [
                "AUTHORITY_OR_THEORY_DRIFT",
                "WRONG_RUN_OR_CYCLE",
                "FUTURE_DATA",
                "DIGEST_OR_SCHEMA_CONFLICT",
                "DUPLICATE_AGENT_OR_OUTCOME_ATTEMPT",
                "RAW_PARSE_BINDING_MISMATCH",
                "UNDEFINED_MAX_LOSS_FOR_NEW_RISK",
                "MODIFIER_WITHOUT_SHARED_DEPENDENCY",
                "HYPOTHESIS_RENEWAL_WITHOUT_NEW_EVIDENCE",
            ],
            "no_retry_repair_or_rule_change_after_sealed_attempt": True,
            "old_failed_run_resume_forbidden": True,
        },
        "authority_boundary": _authority_boundary(),
        "readiness_status": "CONTRACT_ONLY_NOT_AUTHORITY_NOT_RUN_READY",
    }
    return self_digest(document, DIGEST_FIELD)


def verify_v32_experiment_contract_v1(document: Mapping[str, Any]) -> str:
    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V32ExperimentContractError("V32_EXPERIMENT_DOCUMENT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        rebuilt = build_v32_experiment_contract_v1(
            contract_id=document["contract_id"],
            run_id=document["run_id"],
            frozen_at=document["frozen_at"],
            theory_relative_ref=document["theory_binding"]["relative_ref"],
            theory_physical_sha256=document["theory_binding"]["physical_sha256"],
            theory_semantic_digest=document["theory_binding"]["semantic_digest"],
            support_bindings=document["support_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32ExperimentContractError):
            raise
        raise V32ExperimentContractError("V32_EXPERIMENT_DOCUMENT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32ExperimentContractError("V32_EXPERIMENT_RECONSTRUCTION_MISMATCH")
    return supplied


__all__ = [
    "ANALYSIS_INTERVAL_SECONDS",
    "DIGEST_FIELD",
    "INACTIVITY_REVIEW_CYCLES",
    "INACTIVITY_REVIEW_SECONDS",
    "MIN_MARKET_EFFICACY_DECISIONS",
    "OUTCOME_HORIZONS_SECONDS",
    "PILOT_NAME",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "SUPPORT_BINDING_KEYS",
    "THEORY_VERSION",
    "TOTAL_ANALYSIS_CYCLES",
    "TOTAL_OUTCOME_SCHEDULES",
    "V32ExperimentContractError",
    "build_v32_experiment_contract_v1",
    "verify_v32_experiment_contract_v1",
]
