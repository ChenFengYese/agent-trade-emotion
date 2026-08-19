"""Frozen C1.0 catalog used once to create the canonical machine manifest.

The generated JSON manifest, not the Markdown source documents or this module,
is the runtime materialization authority.  Keeping the catalog executable makes
the one-time resolution reproducible and testable while the frozen manifest
retains every resolved entry and digest.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .canonical import canonical_digest, self_digest, verify_self_digest


SCHEMA_VERSION = "1.0.0"
SYSTEM_MODE = "E0_OFFLINE_COUNTERFACTUAL"
EXTERNAL_EXECUTION_AUTHORITY = "NONE_E0"
IMPLEMENTATION_CONTRACT_SHA256 = (
    "8442abe9bf94f358314221e2f97d8e94ce63aae8b560814c8f7f174da5c894b1"
)

BASE_SCHEMA_GROUPS: dict[str, tuple[str, ...]] = {
    "DOMAIN_CONTRACTS": (
        "object_ref",
        "causal_ref",
        "immutable_byte_blob",
        "typed_error",
        "envelope_common_fields",
        "artifact_envelope",
        "event_envelope",
        "schema_registry",
        "object_owner_registry",
        "constraint_registry",
        "closed_error_registry",
        "closed_event_registry",
    ),
    "DOMAIN_EVIDENCE": (
        "field_availability",
        "raw_evidence_record",
        "evidence_source_receipt",
        "evidence_admission_receipt",
        "evidence_bundle",
        "promotion_receipt",
    ),
    "DOMAIN_POLICY": (
        "timeframe_authority_profile",
        "frozen_plugin_registry",
    ),
    "DOMAIN_TIME_AUTHORITY": (
        "review_clock",
        "time_authority_receipt",
    ),
    "DOMAIN_HYPOTHESIS": (
        "competing_hypothesis_set",
        "competing_hypothesis_revision",
        "new_hypothesis_receipt",
    ),
    "DOMAIN_DELIBERATION": (
        "role_contract",
        "role_input_projection_policy",
        "deterministic_predicate_contract",
        "autonomy_envelope",
        "agent_proposal_envelope",
        "proposed_action_plan",
        "challenge_envelope",
        "challenge_claim",
        "challenge_disposition",
        "candidate_bundle",
        "candidate_assembly_receipt",
        "candidate_bundle_set",
        "candidate_calculation_receipt",
        "deterministic_calculation_bundle",
        "constraint_verdict",
        "constraint_verdict_set",
        "feasible_action_set",
        "agent_selection",
    ),
    "DOMAIN_STRATEGIC": (
        "strategic_episode_state",
        "strategic_episode_opened_receipt",
        "transition_receipt",
        "invalidation_receipt",
        "strategic_delta_facet",
    ),
    "DOMAIN_POSITION": (
        "position_lot_reference",
        "position_lock",
        "exposure_reference_receipt",
        "path_payoff_matrix_spec",
        "path_payoff_cell",
        "account_risk_budget_envelope",
        "episode_risk_allocation_receipt",
        "staged_position_plan",
        "stage_spec",
        "stage_activation_receipt",
        "adjustment_quota_contract",
        "plan_amendment_receipt",
        "supervision_availability_contract",
        "unattended_safety_envelope",
        "candidate_risk_receipt",
        "execution_cost_receipt",
        "forward_reward_risk_receipt",
        "position_exposure_facet",
    ),
    "DOMAIN_PORTFOLIO_PROJECTION": ("position_projection_receipt",),
    "DOMAIN_GEOMETRY": (
        "target_reached_event",
        "post_target_hypothesis_review_receipt",
        "geometry_version",
        "geometry_revision_receipt",
        "dynamic_geometry_facet",
    ),
    "DOMAIN_REENTRY": (
        "reentry_contract",
        "reentry_evaluation_receipt",
        "reentry_facet",
    ),
    "DOMAIN_GOVERNANCE": (
        "action_intent",
        "governance_assessment_receipt",
        "counterfactual_policy_receipt",
        "execution_tactic_facet",
    ),
    "DOMAIN_MATCHING": (
        "closed_bar",
        "barrier_event",
        "schedule_gap_receipt",
    ),
    "DOMAIN_EVALUATION": (
        "opportunity_cost_receipt",
        "evaluation_snapshot",
        "ablation_result",
        "hard_gate_result",
    ),
    "APPLICATION_BOOTSTRAP_CONTRACTS": (
        "project_bootstrap_manifest",
        "project_state_genesis_contract",
        "project_state_migration_receipt",
        "cluster_manifest",
        "role_skill_package_manifest",
        "port_contract",
        "kernel_component_contract",
        "skill_resolution_receipt",
        "kernel_component_resolution_receipt",
        "cluster_bootstrap_receipt",
    ),
    "APPLICATION_DECISION_SESSION": (
        "decision_context",
        "role_context_view",
        "resolved_role_input_bundle",
        "resolved_role_input_document",
        "replay_bundle",
        "replay_experiment_arm",
        "open_episode_command",
        "advance_episode_command",
        "governance_decision",
        "timeline_catchup_result",
    ),
    "APPLICATION_COMMIT": ("e0_commit_plan",),
    "INFRASTRUCTURE_AGENT_ADAPTER": (
        "raw_agent_result",
        "raw_agent_turn_archive_manifest",
        "tool_transcript",
    ),
    "INFRASTRUCTURE_LEGACY_ADAPTER": ("legacy_cycle_envelope",),
    "INFRASTRUCTURE_OFFLINE_PORTFOLIO": (
        "portfolio_snapshot",
        "portfolio_replay_result",
        "counterfactual_portfolio_state",
    ),
    "INFRASTRUCTURE_AUTHORITY_ADAPTER": ("authority_snapshot",),
    "INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE": (
        "stored_event",
        "commit_receipt",
        "unit_of_work_batch",
    ),
}

REMOVED_SCHEMAS = frozenset({"stage_activation_receipt"})

ADDED_SCHEMA_GROUPS: dict[str, tuple[str, ...]] = {
    "DOMAIN_POSITION": (
        "episode_risk_budget_envelope",
        "episode_risk_budget_transition_receipt",
        "stage_transition_receipt",
        "supervision_transition_receipt",
        "recursive_feasibility_receipt",
        "receding_horizon_plan",
    ),
    "DOMAIN_TIME_AUTHORITY": (
        "trading_session_calendar_profile",
        "expected_slot_policy",
    ),
    "DOMAIN_MATCHING": (
        "matching_policy_profile",
        "barrier_order_spec",
    ),
    "DOMAIN_POLICY": (
        "data_dependency_contract",
        "plugin_invocation_receipt",
        "calibration_registry",
        "probability_use_authorization",
        "forecast_coherence_receipt",
        "reasoning_strategy_contract",
        "decision_criterion_policy",
    ),
    "DOMAIN_STRATEGIC": ("cross_timescale_control_envelope",),
    "DOMAIN_EVALUATION": (
        "uncertainty_decomposition_receipt",
        "regime_shift_monitor_receipt",
        "forecast_issuance_receipt",
        "outcome_resolution_receipt",
        "calibration_dataset_manifest",
    ),
    "INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE": (
        "aggregate_head_receipt",
        "event_replay_compatibility_manifest",
    ),
}

SCHEMA_FRAGMENT_IDS = frozenset(
    {
        "object_ref",
        "causal_ref",
        "envelope_common_fields",
        "resolved_role_input_document",
    }
)
ENVELOPE_SCHEMA_IDS = frozenset({"artifact_envelope", "event_envelope"})
INLINE_SCHEMA_IDS = frozenset({"action_intent"})

OWNER_OVERRIDES = {
    "immutable_byte_blob": "INFRASTRUCTURE_CONTENT_STORE",
}

CLOSED_ENUMS: dict[str, tuple[str, ...]] = {
    "ProbabilityStatus": ("CALIBRATED_OOS", "ORDINAL_ONLY", "UNKNOWN"),
    "DatasetType": (
        "LEGACY_ACTUAL_INPUT",
        "HISTORICAL_COUNTERFACTUAL_REPLAY",
        "SYNTHETIC_CONTRACT_FIXTURE",
        "INDEPENDENT_FROZEN_EVALUATION",
    ),
    "StrategicStatus": ("ACTIVE", "CHALLENGED", "INVALIDATED", "CLOSED"),
    "ExposureStatus": (
        "FLAT",
        "EXPOSED",
        "RISK_REDUCED",
        "EXIT_PENDING",
        "RECONCILE_PENDING",
    ),
    "WorkflowProjection": (
        "ACTIVE",
        "CHALLENGED",
        "RISK_REDUCED",
        "REENTRY_PENDING",
        "INVALIDATED",
        "CLOSED",
    ),
    "LotRole": ("CORE", "TACTICAL", "HEDGE"),
    "EntryStage": ("PROBE", "CONFIRMED"),
    "StageKind": ("INITIAL", "CONFIRMATION", "TREND"),
    "StageStatus": (
        "REGISTERED",
        "ELIGIBLE",
        "ARMED",
        "COUNTERFACTUAL_FILLED",
        "PROTECTED",
        "PARTIALLY_CLOSED",
        "CLOSED",
        "EXPIRED",
        "CANCELLED",
        "REJECTED",
    ),
    "SupervisionMode": ("SUPERVISED", "UNATTENDED_PROTECTED", "NO_NEW_RISK"),
    "ReentryStatus": (
        "OPEN",
        "DUE",
        "ELIGIBLE",
        "EXECUTED",
        "EXPIRED",
        "CANCELLED_INVALIDATED",
        "CANCELLED_CLOSED",
    ),
    "AnalysisGeometryStatus": (
        "DRAFT",
        "PROPOSED",
        "ACTIVE_ANALYSIS",
        "STALE_FOR_NEW_DECISIONS",
        "SUPERSEDED",
        "EXPIRED",
    ),
    "ExecutionBarrierStatus": (
        "NONE",
        "PENDING_VENUE_ACK",
        "ACTIVE_PROTECTION",
        "SUPERSEDED",
        "TRIGGERED",
        "CANCELLED",
        "REJECTED",
        "ACK_TIMEOUT",
        "HALTED_RECONCILE",
    ),
    "ActionIntent": (
        "KEEP_CORE",
        "ACTIVATE_REGISTERED_STAGE",
        "REDUCE_TACTICAL",
        "PARTIAL_PROFIT",
        "EXIT_STRATEGIC",
        "EXIT_TO_REENTRY_PENDING",
        "REENTER_PARTIAL",
        "NO_ACTION_WITH_OBLIGATION",
    ),
    "ProtectiveActionType": (
        "NONE",
        "TIGHTEN_STOP",
        "TRAIL_CORE",
        "STOP",
        "KILL",
        "PROTECTION_REPAIR",
        "REDUCE_ONLY",
        "EXIT",
        "TIMEOUT",
        "RECONCILIATION",
    ),
    "GeometryOperation": (
        "KEEP",
        "EXPIRE",
        "REBUILD_ANALYTICAL",
        "REVISE_PROTECTION",
    ),
    "AtomicEffectType": (
        "CREATE_REENTRY_CONTRACT",
        "RESERVE_STAGE_RISK",
        "RELEASE_STAGE_RISK",
        "REGISTER_PROTECTIVE_BARRIER",
        "REQUEST_PORTFOLIO_RECONCILIATION",
    ),
    "AggregateType": (
        "STRATEGIC_EPISODE",
        "HYPOTHESIS_SET",
        "POSITION_PLAN",
        "EPISODE_RISK_BUDGET",
        "STAGE",
        "SUPERVISION",
        "GEOMETRY",
        "REENTRY",
        "PORTFOLIO",
        "SCHEDULER_CURSOR",
    ),
    "ChallengeMode": ("POST_PROPOSAL", "BLIND_CONTEXT_ONLY"),
    "ReducerStatus": ("APPLIED", "NO_CHANGE", "REJECTED", "UNKNOWN"),
    "RiskTransitionKind": (
        "ALLOCATE",
        "RESERVE_STAGE",
        "RELEASE_UNUSED_STAGE",
        "OPEN_RISK",
        "PENDING_RISK",
        "REALIZE_LOSS",
        "REALIZE_COST",
        "CLOSE_RISK",
        "RECONCILE",
    ),
    "RegimeStatus": ("NO_SHIFT", "SUSPECTED", "CONFIRMED", "UNKNOWN"),
    "ForecastOutcomeStatus": ("RESOLVED", "PENDING", "CENSORED", "CONFLICTED"),
    "CounterfactualTier": (
        "OBSERVABLE_ACCOUNTING",
        "MODEL_CONDITIONAL",
        "CAUSAL_OPE",
    ),
    "FormalMetricEligibility": ("ELIGIBLE", "DIAGNOSTIC_ONLY", "UNKNOWN"),
    "MarketClockType": ("CONTINUOUS_24_7", "SESSION_CALENDAR"),
    "ScheduleGapStatus": (
        "DETECTED",
        "BAR_RECOVERED",
        "RECOVERED_FULL",
        "PARTIAL_SOURCE_GAP",
        "UNRECOVERABLE",
    ),
    "BarrierType": (
        "KILL",
        "ACCOUNT_MISMATCH",
        "STOP_MARKET",
        "PROTECTION_REPAIR",
        "STRUCTURE_EXIT_MARKET",
        "TARGET_LIMIT",
        "TIMEOUT",
        "ENTRY_STOP_MARKET",
        "ENTRY_LIMIT",
        "BARRIER_UPDATE",
    ),
}

CRITICAL_FIELDS: dict[str, tuple[str, ...]] = {
    "strategic_episode_state": (
        "strategic_episode_id",
        "revision",
        "strategic_status",
        "exposure_status",
        "hypothesis_set_ref",
        "hard_invalidator_refs",
        "review_clock_ref",
        "previous_revision_ref",
    ),
    "proposed_action_plan": (
        "proposed_action_plan_id",
        "strategic_episode_ref",
        "decision_cutoff",
        "path_ref",
        "cross_timescale_control_envelope_ref",
        "action_intent",
        "protective_action_type",
        "geometry_operation",
        "atomic_effect_types",
        "registered_stage_ref",
    ),
    "challenge_envelope": (
        "challenge_mode",
        "proposal_ref",
        "reasoning_strategy_contract_ref",
        "role_context_view_ref",
        "challenge_claim_refs",
        "blinding_proof_ref",
    ),
    "challenge_claim": (
        "proposal_ref",
        "subject_object_refs",
        "claimed_category",
        "source_refs",
        "missing_dependency_refs",
    ),
    "path_payoff_matrix_spec": (
        "path_payoff_matrix_id",
        "strategic_episode_ref",
        "revision",
        "decision_cutoff",
        "planning_context_id",
        "candidate_action_set_digest",
        "row_path_refs",
        "column_action_plan_refs",
        "other_path_ref",
        "unknown_path_ref",
        "probability_status",
        "probability_use_authorization_ref",
    ),
    "path_payoff_cell": (
        "path_ref",
        "action_plan_ref",
        "intermediate_state_refs",
        "terminal_outcome_ref",
        "account_pnl_interval_ref",
        "total_account_risk_ref",
        "marginal_account_risk_ref",
        "data_status",
    ),
    "episode_risk_budget_envelope": (
        "episode_risk_budget_id",
        "strategic_episode_ref",
        "revision",
        "account_risk_budget_envelope_ref",
        "episode_risk_cap_ref",
        "realized_loss_ref",
        "realized_cost_ref",
        "open_risk_ref",
        "pending_risk_ref",
        "reserved_untriggered_stage_risk_ref",
        "tail_reserve_ref",
        "remaining_episode_capacity_ref",
        "risk_reuse_policy",
        "unrealized_profit_credit_ref",
    ),
    "staged_position_plan": (
        "plan_id",
        "strategic_episode_ref",
        "revision",
        "side",
        "episode_risk_budget_ref",
        "path_payoff_matrix_ref",
        "stage_refs",
        "stage_count",
        "supervision_contract_ref",
    ),
    "stage_spec": (
        "stage_id",
        "plan_id",
        "stage_index",
        "stage_kind",
        "entry_stage",
        "lot_role",
        "predecessor_stage_ref",
        "entry_trigger_ref",
        "invalidation_ref",
        "geometry_ref",
        "risk_fraction_ref",
        "expiry",
    ),
    "stage_transition_receipt": (
        "stage_ref",
        "plan_ref",
        "prior_stage_receipt_ref",
        "status_before",
        "status_after",
        "cause_event_ref",
        "decision_cutoff",
        "counterfactual_disposition",
    ),
    "supervision_availability_contract": (
        "supervision_contract_id",
        "strategic_episode_ref",
        "revision",
        "mode_windows",
        "allowed_autonomous_action_intents",
        "allowed_autonomous_protective_actions",
        "allowed_autonomous_geometry_operations",
        "failure_action",
    ),
    "cross_timescale_control_envelope": (
        "envelope_id",
        "strategic_episode_ref",
        "strategic_state_ref",
        "strategic_state_revision",
        "strategic_timeframe_ref",
        "available_at_cutoff",
        "evidence_refs",
        "lease",
        "terminal_safe_action_plan_ref",
    ),
    "recursive_feasibility_receipt": (
        "receipt_id",
        "candidate_action_ref",
        "starting_aggregate_head_refs",
        "planning_horizon_ref",
        "stress_scenario_set",
        "safe_continuation_action_refs",
        "terminal_safe_action_ref",
        "status",
        "failure_reason_codes",
    ),
    "receding_horizon_plan": (
        "receding_horizon_plan_id",
        "strategic_episode_ref",
        "revision",
        "decision_cutoff",
        "planning_context_id",
        "candidate_action_set_digest",
        "current_authorized_action_ref",
        "conditional_continuation_branches",
        "terminal_fallback_action_ref",
        "path_payoff_matrix_ref",
        "recursive_feasibility_receipt_ref",
        "first_step_only",
        "future_branch_authority",
    ),
    "calibration_registry": (
        "calibration_registry_id",
        "registry_version",
        "calibration_record_refs",
        "registry_status",
        "valid_from",
    ),
    "probability_use_authorization": (
        "authorization_id",
        "calibration_record_ref",
        "coherence_receipt_ref",
        "allowed_uses",
        "valid_from",
        "valid_until",
        "fallback_probability_status",
    ),
    "decision_criterion_policy": (
        "decision_criterion_policy_id",
        "revision",
        "hard_constraints_precedence",
        "calibrated_mode_rule",
        "ordinal_mode_rule",
        "unknown_mode_rule",
        "tie_break_order",
        "utility_function_ref",
        "valid_from",
        "valid_until",
    ),
    "opportunity_cost_receipt": (
        "receipt_id",
        "candidate_ref",
        "evaluated_action_ref",
        "comparator_action_ref",
        "comparator_policy_ref",
        "comparator_policy_digest",
        "comparator_frozen_at",
        "decision_cutoff",
        "same_risk_and_authority_constraints",
        "support_overlap_status",
        "counterfactual_tier",
        "not_realized_loss",
        "issued_before_selection",
        "formal_metric_eligibility",
        "status",
    ),
    "aggregate_head_receipt": (
        "aggregate_head_receipt_id",
        "aggregate_id",
        "aggregate_type",
        "aggregate_revision",
        "state_ref",
        "state_digest",
        "last_event_id",
        "last_event_digest",
        "previous_aggregate_head_receipt_ref",
    ),
    "unit_of_work_batch": (
        "batch_id",
        "commit_id",
        "offline_run_id",
        "decision_session_id",
        "idempotent_command_id",
        "idempotency_key",
        "expected_previous_event_sequence",
        "expected_previous_event_digest",
        "expected_aggregate_preconditions",
        "receding_horizon_plan_ref",
        "authorized_first_step_action_ref",
        "atomic_effect_refs",
        "event_envelope_refs",
        "new_aggregate_head_receipt_refs",
        "first_event_sequence",
        "last_event_sequence",
        "new_event_chain_head_digest",
    ),
    "event_replay_compatibility_manifest": (
        "manifest_id",
        "manifest_version",
        "genesis_contract_ref",
        "genesis_state_digest",
        "first_event_sequence",
        "last_event_sequence",
        "expected_event_chain_head_digest",
        "event_schema_version_refs",
        "reducer_version_refs",
        "upcaster_chain",
        "snapshot_manifest",
        "projection_cursor_set",
        "full_replay_expected_digest",
    ),
    "legacy_cycle_envelope": (
        "legacy_cycle_envelope_id",
        "legacy_run_id",
        "cycle_id",
        "freeze_cutoff",
        "decision_submitted_at",
        "source_manifest_ref",
        "field_mapping_entries",
        "gap_entries",
        "integrity_verdict",
        "usage_scope",
    ),
    "forecast_issuance_receipt": (
        "forecast_issuance_id",
        "forecaster_ref",
        "event_definition_ref",
        "forecast_horizon_ref",
        "issued_at",
        "available_at",
        "probability_vector_ref",
        "probability_status_at_issuance",
        "outcome_due_at",
    ),
    "outcome_resolution_receipt": (
        "outcome_resolution_id",
        "forecast_issuance_ref",
        "event_definition_ref",
        "outcome_status",
        "resolved_label_ref",
        "observation_window_start",
        "observation_window_end",
        "label_available_at",
    ),
    "calibration_dataset_manifest": (
        "calibration_dataset_manifest_id",
        "dataset_version",
        "forecast_issuance_refs",
        "outcome_resolution_refs",
        "training_cutoff",
        "evaluation_cutoff",
        "pending_count",
        "censored_count",
        "resolved_count",
        "dataset_type",
    ),
}

FIELD_ENUMS: dict[tuple[str, str], str] = {
    ("strategic_episode_state", "strategic_status"): "StrategicStatus",
    ("strategic_episode_state", "exposure_status"): "ExposureStatus",
    ("proposed_action_plan", "action_intent"): "ActionIntent",
    ("proposed_action_plan", "protective_action_type"): "ProtectiveActionType",
    ("proposed_action_plan", "geometry_operation"): "GeometryOperation",
    ("proposed_action_plan", "atomic_effect_types"): "AtomicEffectType",
    ("challenge_envelope", "challenge_mode"): "ChallengeMode",
    ("path_payoff_matrix_spec", "probability_status"): "ProbabilityStatus",
    ("stage_spec", "stage_kind"): "StageKind",
    ("stage_spec", "entry_stage"): "EntryStage",
    ("stage_spec", "lot_role"): "LotRole",
    ("stage_transition_receipt", "status_after"): "StageStatus",
    ("aggregate_head_receipt", "aggregate_type"): "AggregateType",
    ("recursive_feasibility_receipt", "status"): "ReducerStatus",
    ("forecast_issuance_receipt", "probability_status_at_issuance"): "ProbabilityStatus",
    ("outcome_resolution_receipt", "outcome_status"): "ForecastOutcomeStatus",
    ("calibration_dataset_manifest", "dataset_type"): "DatasetType",
    ("opportunity_cost_receipt", "counterfactual_tier"): "CounterfactualTier",
    ("opportunity_cost_receipt", "formal_metric_eligibility"): "FormalMetricEligibility",
}

ARRAY_FIELD_SUFFIXES = (
    "_refs",
    "_types",
    "_order",
    "_windows",
    "_chain",
    "_manifest",
    "_branches",
    "_preconditions",
    "_reason_codes",
)
BOOLEAN_FIELDS = frozenset(
    {
        "executable",
        "first_step_only",
        "hard_constraints_precedence",
        "not_realized_loss",
        "issued_before_selection",
    }
)
INTEGER_FIELDS = frozenset(
    {
        "revision",
        "stage_index",
        "stage_count",
        "aggregate_revision",
        "first_event_sequence",
        "last_event_sequence",
        "cycle_id",
        "pending_count",
        "censored_count",
        "resolved_count",
    }
)
NULLABLE_FIELDS = frozenset(
    {
        "proposal_ref",
        "blinding_proof_ref",
        "registered_stage_ref",
        "predecessor_stage_ref",
        "prior_stage_receipt_ref",
        "status_before",
        "previous_revision_ref",
        "probability_use_authorization_ref",
        "utility_function_ref",
        "expected_previous_event_sequence",
        "expected_previous_event_digest",
        "resolved_label_ref",
        "label_available_at",
        "unrealized_profit_credit_ref",
        "identification_contract_ref",
    }
)

BASE_ERRORS: dict[str, tuple[str, ...]] = {
    "CONTRACT": ("SCHEMA_INVALID", "PARENT_DIGEST_MISMATCH"),
    "PIT": (
        "PIT_FUTURE_AVAILABLE",
        "PIT_SOURCE_NOT_COMMITTED",
        "PIT_PHYSICAL_EXISTENCE_UNPROVEN",
        "PIT_MIXED_CUTOFF",
    ),
    "STATE": (
        "STATE_HEAD_MISSING",
        "STATE_HEAD_STALE",
        "STATE_ILLEGAL_COMBINATION",
        "STATE_TRANSITION_FORBIDDEN",
    ),
    "GENESIS": (
        "GENESIS_ACTIVE_EPISODE_EXISTS",
        "GENESIS_RECEIPT_MISSING",
        "GENESIS_COOLDOWN_INCOMPLETE",
    ),
    "CLOCK": ("CLOCK_UNTRUSTED", "CLOCK_NOT_DUE", "CLOCK_TIME_INVALID"),
    "EVIDENCE": (
        "EVIDENCE_SOURCE_UNREGISTERED",
        "EVIDENCE_LINEAGE_INVALID",
        "PROMOTION_SELF_SIGNED",
    ),
    "POLICY": (
        "POLICY_DIGEST_MISMATCH",
        "PROFILE_INSTRUMENT_MISMATCH",
        "PLUGIN_REGISTRY_MISMATCH",
        "PLUGIN_DYNAMIC_OPERATION_FORBIDDEN",
    ),
    "GEOMETRY": (
        "GEOMETRY_STALE",
        "GEOMETRY_ACK_MISSING",
        "GEOMETRY_OLD_BARRIER_TRIGGERED",
    ),
    "REENTRY": (
        "REENTRY_CONTRACT_REQUIRED",
        "REENTRY_ELIGIBILITY_REVOKED",
        "REENTRY_OVERDUE",
    ),
    "AUTHORITY": (
        "AUTHORITY_STATUS_MISMATCH",
        "PROMPT_BINDING_MISMATCH",
        "E0_ACTION_AUTHORITY_NONE",
    ),
    "SCHEDULE": (
        "SCHEDULE_SLOT_GAP",
        "SCHEDULE_BAR_GAP",
        "SCHEDULE_CURSOR_NONCONTIGUOUS",
    ),
    "PORTFOLIO": (
        "PORTFOLIO_UNRECONCILED",
        "PORTFOLIO_RESULT_STALE",
        "EPISODE_RISK_EXCEEDED",
    ),
    "BOOTSTRAP_SKILL_KERNEL": (
        "BOOTSTRAP_INCOMPLETE_NO_COMMIT",
        "SKILL_UNAVAILABLE_NO_COMMIT",
        "SKILL_DIGEST_MISMATCH_NO_COMMIT",
        "KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT",
        "KERNEL_COMPONENT_DIGEST_MISMATCH_NO_COMMIT",
        "KERNEL_COMPONENT_HEALTH_UNKNOWN_NO_COMMIT",
    ),
    "AGENT_ROLE": (
        "ROLE_UNAVAILABLE_SESSION_INCOMPLETE",
        "ROLE_INPUT_PROJECTION_INVALID_NO_COMMIT",
        "ROLE_INPUT_BYTES_DIGEST_MISMATCH_NO_COMMIT",
        "PROPOSAL_COVERAGE_INCOMPLETE",
        "CHALLENGE_UNVERIFIED",
        "REPROPOSAL_REQUIRED",
        "CALCULATION_UNKNOWN_DEPENDENCY",
        "SELECTOR_OUTSIDE_FEASIBLE_SET",
    ),
    "COUNTERFACTUAL": (
        "COUNTERFACTUAL_PERMISSION_DENIED",
        "OFFLINE_REPLAY_FAILED_NO_COMMIT",
        "EXTERNAL_EXECUTION_FORBIDDEN_E0",
    ),
    "CONTENT_STORE": (
        "CONTENT_BLOB_DIGEST_MISMATCH",
        "CONTENT_KEY_COLLISION",
    ),
    "COMMIT": ("UOW_HEAD_STALE", "UOW_PARTIAL_DUPLICATE", "UOW_RECOVERY_REQUIRED"),
}

EXTRA_ERROR_GROUPS: dict[str, tuple[str, ...]] = {
    "STRATEGIC": (
        "STRATEGIC_PRIOR_HEAD_MISMATCH",
        "STRATEGIC_ILLEGAL_TRANSITION",
        "STRATEGIC_PREMISE_MAPPING_MISSING",
        "STRATEGIC_TIME_AUTHORITY_MISSING",
        "STRATEGIC_INVALIDATOR_UNREGISTERED",
        "STRATEGIC_REENTRY_ATOMICITY_MISSING",
        "STRATEGIC_CLOSE_PRECONDITION_FAILED",
    ),
    "STAGE": (
        "STAGE_UNREGISTERED",
        "STAGE_PRIOR_RECEIPT_MISMATCH",
        "STAGE_PREDECESSOR_FAILED",
        "STAGE_TRIGGER_UNKNOWN",
        "STAGE_EXPIRY_REACHED",
        "STAGE_TERMINAL_REUSE",
        "STAGE_FORWARD_RR_INELIGIBLE",
        "STAGE_RISK_CAP_FAILED",
        "STAGE_SUPERVISION_FORBIDDEN",
        "STAGE_PROTECTION_ATOMICITY_UNKNOWN",
        "STAGE_HEDGE_FORBIDDEN_E0",
        "STAGE_REAL_ADD_AUTHORITY_NONE",
    ),
    "RISK": (
        "RISK_ACCOUNT_ENVELOPE_MISSING",
        "RISK_EPISODE_ALLOCATION_MISSING",
        "RISK_COMPONENT_UNIT_MISMATCH",
        "RISK_ACCOUNT_CAP_BREACH",
        "RISK_EPISODE_CAP_BREACH",
        "RISK_STAGE_RESERVATION_BREACH",
        "RISK_UNREALIZED_PROFIT_RECYCLING",
        "RISK_REALIZED_LOSS_RESET",
        "RISK_CROSS_EPISODE_REALLOCATION_UNAUTHORIZED",
        "RISK_PORTFOLIO_TRUTH_UNKNOWN",
    ),
    "SUPERVISION": (
        "SUPERVISION_WINDOW_MISSING",
        "SUPERVISION_WINDOW_OVERLAP",
        "SUPERVISION_PROTECTION_UNKNOWN",
        "SUPERVISION_ACK_STALE",
        "SUPERVISION_DATA_STALE",
        "SUPERVISION_ACCOUNT_UNRECONCILED",
        "SUPERVISION_WORST_CASE_LOSS_UNKNOWN",
        "SUPERVISION_NEW_RISK_FORBIDDEN",
    ),
    "GEOMETRY": (
        "GEOMETRY_PRIOR_VERSION_MISMATCH",
        "GEOMETRY_ANALYSIS_TRANSITION_ILLEGAL",
        "GEOMETRY_PROTECTION_TRANSITION_ILLEGAL",
        "GEOMETRY_STOP_LOOSEN_FORBIDDEN",
        "GEOMETRY_HORIZON_EXTENSION_FORBIDDEN",
        "GEOMETRY_T023_GATE_UNCALIBRATED",
        "GEOMETRY_OLD_BARRIER_ALREADY_CROSSED",
    ),
    "REENTRY": (
        "REENTRY_ATOMIC_OPEN_MISSING",
        "REENTRY_PRIOR_STATE_MISMATCH",
        "REENTRY_REVIEW_OVERDUE",
        "REENTRY_DEFERRAL_LIMIT_MISSING",
        "REENTRY_DEFERRAL_LIMIT_EXCEEDED",
        "REENTRY_CURRENT_ELIGIBILITY_FAILED",
        "REENTRY_NEW_THI_MISSING",
        "REENTRY_RISK_PERMISSION_MISSING",
        "REENTRY_CORE_FILL_UNRECONCILED",
    ),
    "DELIBERATION": (
        "ACTION_INTENT_UNKNOWN",
        "PROTECTIVE_ACTION_TYPE_UNKNOWN",
        "GEOMETRY_OPERATION_UNKNOWN",
        "ACTION_FACET_INCOMPATIBLE",
        "CANDIDATE_STAGE_REF_MISSING",
        "CANDIDATE_THEORY_ACTION_OMITTED",
        "CANDIDATE_HEDGE_FORBIDDEN_E0",
        "CONSTRAINT_UNREGISTERED",
        "CONSTRAINT_SOFT_REMOVAL_FORBIDDEN",
        "FEASIBLE_SET_INCOMPLETE",
        "FEASIBLE_SET_NO_ACTION_MISSING",
        "SELECTION_CRITERION_POLICY_MISMATCH",
        "SELECTION_ABSTAIN_OBLIGATION_MISSING",
        "RECURSIVE_FEASIBILITY_NOT_PASS",
        "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED",
        "PROBABILITY_USE_UNAUTHORIZED_E0",
    ),
    "SCHEDULE": (
        "SCHEDULE_CALENDAR_PROFILE_MISSING",
        "SCHEDULE_EXPECTED_SLOT_POLICY_MISSING",
        "SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS",
        "SCHEDULE_CORPORATE_ACTION_UNKNOWN",
        "SCHEDULE_STRATEGIC_REVIEW_UNRECOVERABLE",
    ),
    "MATCHING": (
        "MATCHING_POLICY_MISSING",
        "MATCHING_MULTIPLIER_UNKNOWN",
        "MATCHING_TICK_OR_STEP_UNKNOWN",
        "MATCHING_COST_POLICY_UNKNOWN",
        "MATCHING_BAR_LINEAGE_INVALID",
        "MATCHING_BARRIER_INACTIVE",
        "MATCHING_LIMIT_TOUCH_INSUFFICIENT",
        "MATCHING_PARTIAL_FILL_UNIDENTIFIED",
        "MATCHING_AMBIGUOUS_BARRIER_ORDER",
        "MATCHING_CANCEL_REPLACE_ACK_UNKNOWN",
        "MATCHING_FUTURE_BAR_FORBIDDEN",
    ),
    "LEGACY": (
        "LEGACY_CYCLE_OUT_OF_SCOPE",
        "LEGACY_CYCLE_0025_DECISION_ABSENT",
        "LEGACY_MANIFEST_DIGEST_MISMATCH",
        "LEGACY_LEDGER_OR_TRANSACTION_INVALID",
        "LEGACY_FIELD_MAPPING_AMBIGUOUS",
        "LEGACY_PHYSICAL_EXISTENCE_UNPROVEN",
        "LEGACY_WRITE_ATTEMPT_FORBIDDEN",
    ),
}

BASE_EVENTS: dict[str, tuple[str, str, str]] = {
    "DECISION_SESSION_BOOTSTRAPPED": (
        "APPLICATION_DECISION_SESSION",
        "cluster_bootstrap_receipt",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "AGENT_PROPOSAL_FROZEN": (
        "DOMAIN_DELIBERATION",
        "agent_proposal_envelope",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "CHALLENGE_FROZEN": (
        "DOMAIN_DELIBERATION",
        "challenge_envelope",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "CHALLENGE_DISPOSITIONED": (
        "DOMAIN_DELIBERATION",
        "challenge_disposition",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "CANDIDATE_BUNDLES_ASSEMBLED": (
        "DOMAIN_DELIBERATION",
        "candidate_bundle_set",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "FEASIBLE_ACTION_SET_BUILT": (
        "DOMAIN_DELIBERATION",
        "feasible_action_set",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "AGENT_SELECTION_FROZEN": (
        "DOMAIN_DELIBERATION",
        "agent_selection",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "REPLAY_BUNDLE_FROZEN": (
        "APPLICATION_DECISION_SESSION",
        "replay_bundle",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "EVIDENCE_SOURCE_FETCHED": (
        "DOMAIN_EVIDENCE",
        "evidence_source_receipt",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "EVIDENCE_ADMITTED": (
        "DOMAIN_EVIDENCE",
        "evidence_admission_receipt",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "EVIDENCE_REJECTED": (
        "DOMAIN_EVIDENCE",
        "typed_error",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "SIGNAL_PROMOTED": ("DOMAIN_EVIDENCE", "promotion_receipt", "COMMITTED_DOMAIN_TRANSITION"),
    "HYPOTHESIS_CREATED": (
        "DOMAIN_HYPOTHESIS",
        "new_hypothesis_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "HYPOTHESIS_REVISED": (
        "DOMAIN_HYPOTHESIS",
        "competing_hypothesis_revision",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "EPISODE_OPENED": (
        "DOMAIN_STRATEGIC",
        "strategic_episode_opened_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "STRATEGIC_STATE_TRANSITIONED": (
        "DOMAIN_STRATEGIC",
        "transition_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "STRATEGIC_INVALIDATED": (
        "DOMAIN_STRATEGIC",
        "invalidation_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "EXPOSURE_REFERENCE_LOCKED": (
        "DOMAIN_POSITION",
        "exposure_reference_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "POSITION_PROJECTED": (
        "DOMAIN_PORTFOLIO_PROJECTION",
        "position_projection_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "TARGET_REACHED": ("DOMAIN_GEOMETRY", "target_reached_event", "COMMITTED_DOMAIN_TRANSITION"),
    "POST_TARGET_REVIEWED": (
        "DOMAIN_GEOMETRY",
        "post_target_hypothesis_review_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "GEOMETRY_STALE_FOR_DECISIONS": (
        "DOMAIN_GEOMETRY",
        "geometry_revision_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "GEOMETRY_ACTIVATED": (
        "DOMAIN_GEOMETRY",
        "geometry_revision_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "REENTRY_OPENED": ("DOMAIN_REENTRY", "reentry_contract", "COMMITTED_DOMAIN_TRANSITION"),
    "REENTRY_DUE": (
        "DOMAIN_REENTRY",
        "time_authority_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "REENTRY_EVALUATED": (
        "DOMAIN_REENTRY",
        "reentry_evaluation_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "REENTRY_TERMINATED": (
        "DOMAIN_REENTRY",
        "reentry_evaluation_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "GOVERNANCE_ASSESSED": (
        "DOMAIN_GOVERNANCE",
        "governance_assessment_receipt",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "COUNTERFACTUAL_POLICY_CREATED": (
        "DOMAIN_GOVERNANCE",
        "counterfactual_policy_receipt",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "SCHEDULE_GAP_DETECTED": (
        "DOMAIN_MATCHING",
        "schedule_gap_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "BAR_REPLAYED": ("DOMAIN_MATCHING", "closed_bar", "COMMITTED_DOMAIN_TRANSITION"),
    "BARRIER_TRIGGERED": ("DOMAIN_MATCHING", "barrier_event", "COMMITTED_DOMAIN_TRANSITION"),
    "PORTFOLIO_REPLAYED": (
        "INFRASTRUCTURE_OFFLINE_PORTFOLIO",
        "portfolio_replay_result",
        "PRECOMMIT_RECORDED_AT_FINAL_COMMIT",
    ),
    "PORTFOLIO_RECONCILED": (
        "DOMAIN_PORTFOLIO_PROJECTION",
        "position_projection_receipt",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "HORIZON_EVALUATED": (
        "DOMAIN_EVALUATION",
        "evaluation_snapshot",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
    "HARD_GATES_EVALUATED": (
        "DOMAIN_EVALUATION",
        "hard_gate_result",
        "COMMITTED_DOMAIN_TRANSITION",
    ),
}

EXTRA_EVENTS = frozenset(
    {
        "CROSS_TIMESCALE_ENVELOPE_ISSUED",
        "CROSS_TIMESCALE_ENVELOPE_EXPIRED",
        "LOWER_TIMEFRAME_PROMOTION_REQUESTED",
        "RECURSIVE_FEASIBILITY_EVALUATED",
        "RECEDING_HORIZON_PLAN_RECORDED",
        "RECEDING_HORIZON_REVIEW_DUE",
        "CALIBRATION_REGISTRY_MATERIALIZED",
        "PROBABILITY_USE_AUTHORIZATION_REVOKED",
        "FORECAST_COHERENCE_EVALUATED",
        "UNCERTAINTY_DECOMPOSED",
        "REGIME_SHIFT_MONITORED",
        "REGIME_REVIEW_REQUESTED",
        "AGGREGATE_HEAD_COMMITTED",
        "EVENT_REPLAY_COMPATIBILITY_VERIFIED",
        "REASONING_STRATEGY_RESOLVED",
        "DECISION_CRITERION_POLICY_FROZEN",
        "FORECAST_ISSUED",
        "OUTCOME_RESOLUTION_RECORDED",
        "CALIBRATION_DATASET_FROZEN",
        "PROPOSED_ACTION_PLAN_RECORDED",
        "PATH_PAYOFF_MATRIX_CALCULATED",
        "OPPORTUNITY_COMPARATOR_EVALUATED",
        "UNIT_OF_WORK_COMMITTED",
        "STRATEGIC_STATE_ADVANCED",
        "STRATEGIC_CHALLENGED",
        "STRATEGIC_CHALLENGE_RESOLVED",
        "STRATEGIC_CLOSED",
        "EXPOSURE_STATE_DERIVED",
        "STAGE_REGISTERED",
        "STAGE_ELIGIBLE",
        "STAGE_ARMED",
        "STAGE_COUNTERFACTUAL_FILLED",
        "STAGE_PROTECTED",
        "STAGE_PARTIALLY_CLOSED",
        "STAGE_CLOSED",
        "STAGE_EXPIRED",
        "STAGE_CANCELLED",
        "STAGE_REJECTED",
        "EPISODE_RISK_ALLOCATED",
        "STAGE_RISK_RESERVED",
        "STAGE_RISK_RELEASED_UNUSED",
        "PENDING_RISK_UPDATED",
        "OPEN_RISK_UPDATED",
        "RISK_LOSS_REALIZED",
        "RISK_COST_REALIZED",
        "RISK_RECONCILED",
        "SUPERVISION_MODE_CHANGED",
        "UNATTENDED_PROTECTION_FAILED",
        "NO_NEW_RISK_ENTERED",
        "ANALYSIS_GEOMETRY_ACTIVATED",
        "ANALYSIS_GEOMETRY_STALED",
        "ANALYSIS_GEOMETRY_SUPERSEDED",
        "ANALYSIS_GEOMETRY_EXPIRED",
        "PROTECTION_REPLACEMENT_REQUESTED",
        "PROTECTION_ACTIVATED",
        "PROTECTION_TRIGGERED",
        "PROTECTION_REPLACEMENT_FAILED",
        "REENTRY_ELIGIBLE",
        "REENTRY_DEFERRED",
        "REENTRY_EXPIRED",
        "REENTRY_CANCELLED_INVALIDATED",
        "REENTRY_CANCELLED_CLOSED",
        "REENTRY_EXECUTED",
        "PROPOSAL_RECORDED",
        "CHALLENGE_RECORDED",
        "CHALLENGE_DISPOSITION_RECORDED",
        "CANDIDATES_ASSEMBLED",
        "CANDIDATES_CALCULATED",
        "CONSTRAINTS_EVALUATED",
        "FEASIBLE_SET_BUILT",
        "AGENT_SELECTION_RECORDED",
        "WAKE_ASSESSED",
        "SCHEDULE_GAP_TERMINAL",
        "BAR_CONTINUITY_VERIFIED",
        "BARRIER_CURSOR_ADVANCED",
        "WAKE_CURSOR_ADVANCED",
        "STRATEGIC_REVIEW_CURSOR_ADVANCED",
        "BARRIER_EVALUATED",
        "STOP_HIT",
        "TARGET_HIT",
        "TIMEOUT_HIT",
        "ENTRY_TRIGGERED",
        "AMBIGUOUS_BARRIER_ORDER_RECORDED",
        "COUNTERFACTUAL_FILL_RECORDED",
        "PARTIAL_FILL_RECORDED",
        "ORDER_NO_FILL_RECORDED",
        "CANCEL_REPLACE_ACK_RECORDED",
        "PORTFOLIO_RECONCILIATION_REQUIRED",
    }
)

CONSTRAINT_IDS = (
    "CROSS_TIMESCALE_LEASE_CURRENT",
    "LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN",
    "ACTION_FACETS_CLOSED_AND_COMPATIBLE",
    "BLIND_CHALLENGE_PROPOSAL_HIDDEN",
    "REENTRY_CREATION_ATOMIC_EFFECT_REQUIRED",
    "RECURSIVE_FEASIBILITY_PASS_REQUIRED_FOR_NEW_RISK",
    "RECEDING_HORIZON_FIRST_STEP_ONLY",
    "PROBABILITY_USE_AUTHORIZATION_REQUIRED",
    "CALIBRATION_LINEAGE_COMPLETE",
    "REGIME_SIGNAL_NO_TRADE_AUTHORITY",
    "AGGREGATE_EXPECTED_REVISION_AND_DIGEST_MATCH",
    "PROJECTION_NOT_COMMAND_HEAD",
    "OPPORTUNITY_COMPARATOR_FROZEN_AND_FEASIBLE",
    "DECISION_CRITERION_POLICY_BOUND",
    "REASONING_OUTPUT_UNTRUSTED",
    "REGISTERED_STAGE_REQUIRED",
    "STAGE_NOT_EXPIRED",
    "STAGE_PREDECESSOR_SATISFIED",
    "STAGE_TRIGGER_PIT_SATISFIED",
    "INDEPENDENT_GEOMETRY_REQUIRED",
    "FORWARD_RR_POLICY_IDENTIFIED",
    "ACCOUNT_RISK_CAP_NOT_EXCEEDED",
    "EPISODE_RISK_CAP_NOT_EXCEEDED",
    "STAGE_RESERVED_RISK_CAP_NOT_EXCEEDED",
    "PORTFOLIO_MARGINAL_STRESS_CAP_NOT_EXCEEDED",
    "UNREALIZED_PROFIT_SUBSIDY_FORBIDDEN",
    "SUPERVISION_MODE_COMPATIBLE",
    "UNATTENDED_ATOMIC_PROTECTION_REQUIRED",
    "ZERO_CORE_REENTRY_CONTRACT_REQUIRED",
    "NO_ACTION_OBLIGATION_REQUIRED",
    "SELECTOR_FEASIBLE_SET_MEMBERSHIP",
    "CURRENT_CORE_ADD_COUNTERFACTUAL_ONLY",
    "EXTERNAL_EXECUTION_FORBIDDEN_E0",
)

PLUGIN_TYPES = (
    "EVIDENCE_SOURCE",
    "NORMAL_RANGE_POLICY",
    "EVENT_QUALIFICATION_POLICY",
    "RISK_POLICY",
    "HORIZON_POLICY",
    "CALIBRATION_METHOD",
    "ROBUST_OPTIMIZATION",
    "ENSEMBLE_FORECAST",
    "CHANGE_POINT_MONITOR",
)


def resolved_schema_owners() -> dict[str, str]:
    result: dict[str, str] = {}
    for owner, schema_ids in BASE_SCHEMA_GROUPS.items():
        for schema_id in schema_ids:
            if schema_id not in REMOVED_SCHEMAS:
                result[schema_id] = owner
    for owner, schema_ids in ADDED_SCHEMA_GROUPS.items():
        for schema_id in schema_ids:
            if schema_id in result:
                raise ValueError(f"duplicate schema identity: {schema_id}")
            result[schema_id] = owner
    return dict(sorted(result.items()))


def schema_contract_fields(schema_id: str) -> tuple[str, ...]:
    if schema_id in CRITICAL_FIELDS:
        return CRITICAL_FIELDS[schema_id]
    if schema_id.endswith("_registry"):
        return ("registry_id", "registry_version", "entries", "closed")
    if schema_id.endswith("_manifest"):
        return ("manifest_id", "manifest_version", "entry_refs")
    if schema_id.endswith("_receipt"):
        return ("receipt_id", "source_refs", "verdict")
    if schema_id.endswith("_state"):
        return ("state_id", "revision", "status", "previous_revision_ref")
    if schema_id.endswith("_contract"):
        return ("contract_id", "contract_version", "input_refs", "output_refs")
    if schema_id.endswith("_profile"):
        return ("profile_id", "profile_version", "rule_refs")
    if schema_id.endswith("_plan"):
        return ("plan_id", "revision", "action_refs")
    if schema_id.endswith("_set"):
        return ("set_id", "item_refs")
    if schema_id.endswith("_facet"):
        return ("facet_id", "subject_ref", "proposed_value_refs")
    if schema_id.endswith("_bundle"):
        return ("bundle_id", "item_refs")
    if schema_id.endswith("_event"):
        return ("event_id", "occurred_at", "payload_refs")
    if schema_id.endswith("_command"):
        return ("command_id", "idempotency_key", "input_refs")
    if schema_id.endswith("_envelope"):
        return ("envelope_id", "revision", "content_refs")
    return ("record_id", "revision", "value_refs")


def schema_kind(schema_id: str) -> str:
    if schema_id in SCHEMA_FRAGMENT_IDS:
        return "SCHEMA_FRAGMENT"
    if schema_id in ENVELOPE_SCHEMA_IDS:
        return "ENVELOPE"
    if schema_id in INLINE_SCHEMA_IDS:
        return "INLINE_VALUE"
    return "OWNER_PAYLOAD"


def digest_field_name(schema_id: str) -> str | None:
    if schema_kind(schema_id) in {"SCHEMA_FRAGMENT", "INLINE_VALUE"}:
        return None
    if schema_id.endswith("_registry"):
        return "registry_digest"
    if schema_id.endswith("_manifest"):
        return "manifest_digest"
    if schema_id.endswith("_receipt"):
        return "receipt_digest"
    if schema_id.endswith("_state"):
        return "state_digest"
    if schema_id.endswith("_contract"):
        return "contract_digest"
    if schema_id.endswith("_profile"):
        return "profile_digest"
    if schema_id.endswith("_plan"):
        return "plan_digest"
    if schema_id.endswith("_set"):
        return "set_digest"
    if schema_id.endswith("_bundle"):
        return "bundle_digest"
    if schema_id.endswith("_event"):
        return "event_digest"
    if schema_id.endswith("_envelope"):
        return "envelope_digest"
    return "record_digest"


def field_schema(schema_id: str, field_name: str) -> dict[str, Any]:
    enum_name = FIELD_ENUMS.get((schema_id, field_name))
    if enum_name:
        values = CLOSED_ENUMS[enum_name]
        base: dict[str, Any]
        if field_name.endswith(("_refs", "_types")):
            base = {
                "type": "array",
                "items": {"type": "string", "enum": list(values)},
                "uniqueItems": True,
            }
        else:
            base = {"type": "string", "enum": list(values)}
    elif field_name in BOOLEAN_FIELDS:
        base = {"type": "boolean"}
    elif field_name in INTEGER_FIELDS:
        base = {"type": "integer", "minimum": 0}
    elif field_name.endswith(ARRAY_FIELD_SUFFIXES):
        base = {"type": "array", "items": {"type": "string"}}
    elif field_name in {"lease", "stress_scenario_set"}:
        base = {
            "type": "object",
            "additionalProperties": False,
            "required": ["object_id", "object_digest"],
            "properties": {
                "object_id": {"type": "string", "minLength": 1},
                "object_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
        }
    elif field_name.endswith(("_at", "_from", "_until", "_cutoff", "_start", "_end")):
        base = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T.*Z$"}
    elif field_name.endswith("_digest"):
        base = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    else:
        base = {"type": "string", "minLength": 1}
    if field_name in NULLABLE_FIELDS:
        return {"anyOf": [base, {"type": "null"}]}
    return base


def schema_document(entry: Mapping[str, Any]) -> dict[str, Any]:
    schema_id = str(entry["schema_id"])
    fields = tuple(entry["required_fields"])
    properties: dict[str, Any] = {
        "schema_id": {"const": schema_id},
        "schema_version": {"const": SCHEMA_VERSION},
    }
    for field_name in fields:
        properties[field_name] = field_schema(schema_id, field_name)
    kind = str(entry["schema_kind"])
    required = ["schema_id", "schema_version", *fields]
    if kind not in {"SCHEMA_FRAGMENT", "INLINE_VALUE"}:
        properties.update(
            {
                "system_mode": {"const": SYSTEM_MODE},
                "external_execution_authority": {
                    "const": EXTERNAL_EXECUTION_AUTHORITY
                },
                "executable": {"const": False},
            }
        )
        required.extend(
            ["system_mode", "external_execution_authority", "executable"]
        )
        digest_field = entry["payload_self_digest_field_name"]
        if digest_field:
            properties[digest_field] = {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            }
            required.append(str(digest_field))
    if schema_id == "action_intent":
        properties = {
            "schema_id": {"const": schema_id},
            "schema_version": {"const": SCHEMA_VERSION},
            "action_intent": {
                "type": "string",
                "enum": list(CLOSED_ENUMS["ActionIntent"]),
            },
            "protective_action_type": {
                "type": "string",
                "enum": list(CLOSED_ENUMS["ProtectiveActionType"]),
            },
            "geometry_operation": {
                "type": "string",
                "enum": list(CLOSED_ENUMS["GeometryOperation"]),
            },
        }
        required = list(properties)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:theory-agent-v2:{schema_id}:{SCHEMA_VERSION}",
        "title": f"{schema_id}.v1",
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def _retryability(error_code: str) -> str:
    if error_code.startswith("UOW_") or "HEAD_STALE" in error_code:
        return "IDEMPOTENT_RETRY"
    if any(
        token in error_code
        for token in (
            "MISSING",
            "UNKNOWN",
            "STALE",
            "UNAVAILABLE",
            "INCOMPLETE",
            "UNRECONCILED",
            "MISMATCH",
            "GAP",
        )
    ):
        return "AFTER_INPUT_REPAIR"
    return "NEVER"


def _error_entries() -> list[dict[str, Any]]:
    merged: dict[str, str] = {}
    for category, codes in (*BASE_ERRORS.items(), *EXTRA_ERROR_GROUPS.items()):
        for code in codes:
            prior = merged.get(code)
            if prior is not None and prior != category:
                # The more specific reducer category wins over the baseline.
                if category in EXTRA_ERROR_GROUPS:
                    merged[code] = category
            else:
                merged[code] = category
    return [
        {
            "error_code": code,
            "category": category,
            "fail_closed": True,
            "retryability": _retryability(code),
            "required_reason_field_names": [],
        }
        for code, category in sorted(merged.items())
    ]


def _event_metadata(event_type: str) -> tuple[str, str, str]:
    if event_type in BASE_EVENTS:
        return BASE_EVENTS[event_type]
    if event_type == "UNIT_OF_WORK_COMMITTED":
        return (
            "INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE",
            "unit_of_work_batch",
            "POST_COMMIT_NOTIFICATION",
        )
    prefix_map = (
        (("STAGE_", "RISK_", "OPEN_RISK", "PENDING_RISK", "EPISODE_RISK", "SUPERVISION_", "NO_NEW_RISK"), "DOMAIN_POSITION", "stage_transition_receipt"),
        (("REENTRY_",), "DOMAIN_REENTRY", "reentry_evaluation_receipt"),
        (("STRATEGIC_", "EXPOSURE_"), "DOMAIN_STRATEGIC", "transition_receipt"),
        (("ANALYSIS_GEOMETRY_", "PROTECTION_"), "DOMAIN_GEOMETRY", "geometry_revision_receipt"),
        (("BARRIER_", "STOP_", "TARGET_", "TIMEOUT_", "ENTRY_", "AMBIGUOUS_", "COUNTERFACTUAL_FILL_", "PARTIAL_FILL_", "ORDER_NO_FILL_", "CANCEL_REPLACE_", "WAKE_", "SCHEDULE_", "BAR_CONTINUITY_"), "DOMAIN_MATCHING", "barrier_event"),
        (("PROPOSAL_", "CHALLENGE_", "CANDIDATES_", "CONSTRAINTS_", "FEASIBLE_SET_", "AGENT_SELECTION_", "PROPOSED_ACTION_"), "DOMAIN_DELIBERATION", "candidate_bundle_set"),
        (("CALIBRATION_", "PROBABILITY_", "REASONING_", "DECISION_CRITERION_"), "DOMAIN_POLICY", "typed_error"),
        (("FORECAST_", "OUTCOME_", "UNCERTAINTY_", "REGIME_", "PATH_PAYOFF_", "OPPORTUNITY_"), "DOMAIN_EVALUATION", "evaluation_snapshot"),
        (("CROSS_TIMESCALE_", "LOWER_TIMEFRAME_"), "DOMAIN_STRATEGIC", "cross_timescale_control_envelope"),
        (("RECURSIVE_", "RECEDING_"), "DOMAIN_POSITION", "recursive_feasibility_receipt"),
        (("AGGREGATE_", "EVENT_REPLAY_"), "INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE", "aggregate_head_receipt"),
        (("PORTFOLIO_RECONCILIATION_",), "DOMAIN_PORTFOLIO_PROJECTION", "position_projection_receipt"),
    )
    for prefixes, owner, payload in prefix_map:
        if event_type.startswith(prefixes):
            return owner, payload, "COMMITTED_DOMAIN_TRANSITION"
    return "DOMAIN_CONTRACTS", "typed_error", "PRECOMMIT_RECORDED_AT_FINAL_COMMIT"


def _event_entries() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event_type in sorted(set(BASE_EVENTS) | set(EXTRA_EVENTS)):
        owner, payload_schema_id, trigger_class = _event_metadata(event_type)
        result.append(
            {
                "event_type": event_type,
                "unique_owner_module": owner,
                "payload_schema_id": payload_schema_id,
                "payload_schema_version": SCHEMA_VERSION,
                "trigger_class": trigger_class,
                "idempotency_key_field_names": [
                    "offline_run_id",
                    "event_sequence",
                ],
                "post_commit_listener_ids": [],
                "same_batch_commit_receipt_reference": False,
            }
        )
    return result


def _constraint_entries() -> list[dict[str, Any]]:
    session_global = {
        "AGGREGATE_EXPECTED_REVISION_AND_DIGEST_MATCH",
        "PROJECTION_NOT_COMMAND_HEAD",
        "DECISION_CRITERION_POLICY_BOUND",
        "REASONING_OUTPUT_UNTRUSTED",
        "CALIBRATION_LINEAGE_COMPLETE",
    }
    return [
        {
            "constraint_id": constraint_id,
            "unique_owner_module": "DOMAIN_GOVERNANCE",
            "constraint_class": "HARD",
            "evaluator_id": f"theory_agent_v2.constraint.{constraint_id.lower()}",
            "evaluator_version": SCHEMA_VERSION,
            "evaluator_contract_digest": canonical_digest(
                {
                    "constraint_id": constraint_id,
                    "version": SCHEMA_VERSION,
                    "result": "PASS_FAIL_UNKNOWN",
                }
            ),
            "unknown_disposition": (
                "SESSION_NO_COMMIT"
                if constraint_id in session_global
                else "CANDIDATE_UNKNOWN_REMOVE"
            ),
            "verdict_schema_id": "constraint_verdict",
            "applicable_action_intents": list(CLOSED_ENUMS["ActionIntent"]),
            "applicable_protective_actions": list(
                CLOSED_ENUMS["ProtectiveActionType"]
            ),
            "applicable_geometry_operations": list(
                CLOSED_ENUMS["GeometryOperation"]
            ),
        }
        for constraint_id in sorted(CONSTRAINT_IDS)
    ]


def _transition_tables() -> dict[str, list[dict[str, str]]]:
    return {
        "StrategicStatus": [
            {"from": "GENESIS", "to": "ACTIVE"},
            {"from": "ACTIVE", "to": "ACTIVE"},
            {"from": "ACTIVE", "to": "CHALLENGED"},
            {"from": "CHALLENGED", "to": "ACTIVE"},
            {"from": "CHALLENGED", "to": "CHALLENGED"},
            {"from": "ACTIVE", "to": "INVALIDATED"},
            {"from": "CHALLENGED", "to": "INVALIDATED"},
            {"from": "ACTIVE", "to": "CLOSED"},
            {"from": "CHALLENGED", "to": "CLOSED"},
            {"from": "INVALIDATED", "to": "CLOSED"},
        ],
        "StageStatus": [
            {"from": "GENESIS", "to": "REGISTERED"},
            {"from": "REGISTERED", "to": "ELIGIBLE"},
            {"from": "REGISTERED", "to": "EXPIRED"},
            {"from": "REGISTERED", "to": "CANCELLED"},
            {"from": "REGISTERED", "to": "REJECTED"},
            {"from": "ELIGIBLE", "to": "ARMED"},
            {"from": "ELIGIBLE", "to": "REGISTERED"},
            {"from": "ARMED", "to": "COUNTERFACTUAL_FILLED"},
            {"from": "ARMED", "to": "ELIGIBLE"},
            {"from": "COUNTERFACTUAL_FILLED", "to": "PROTECTED"},
            {"from": "PROTECTED", "to": "PARTIALLY_CLOSED"},
            {"from": "PROTECTED", "to": "CLOSED"},
            {"from": "PARTIALLY_CLOSED", "to": "CLOSED"},
        ],
        "ReentryStatus": [
            {"from": "GENESIS", "to": "OPEN"},
            {"from": "OPEN", "to": "DUE"},
            {"from": "DUE", "to": "ELIGIBLE"},
            {"from": "DUE", "to": "OPEN"},
            {"from": "ELIGIBLE", "to": "DUE"},
            {"from": "ELIGIBLE", "to": "EXECUTED"},
            {"from": "OPEN", "to": "EXPIRED"},
            {"from": "DUE", "to": "EXPIRED"},
            {"from": "ELIGIBLE", "to": "EXPIRED"},
        ],
    }


def build_canonical_manifest() -> dict[str, Any]:
    owners = resolved_schema_owners()
    if len(owners) != 142:
        raise ValueError(f"resolved schema identity count mismatch: {len(owners)}")
    schema_entries: list[dict[str, Any]] = []
    object_owner_entries: list[dict[str, Any]] = []
    schema_contracts: list[dict[str, Any]] = []
    for schema_id, owner in owners.items():
        kind = schema_kind(schema_id)
        digest_field = digest_field_name(schema_id)
        contract = {
            "schema_id": schema_id,
            "schema_version": SCHEMA_VERSION,
            "schema_kind": kind,
            "unique_owner_module": owner,
            "required_fields": list(schema_contract_fields(schema_id)),
            "payload_self_digest_field_name": digest_field,
        }
        document = schema_document(contract)
        schema_digest = canonical_digest(document)
        schema_entries.append(
            {
                **contract,
                "schema_bytes_digest": schema_digest,
                "compatibility_policy": (
                    "REJECT_UNKNOWN_MAJOR_PRESERVE_KNOWN_OPTIONAL"
                ),
            }
        )
        schema_contracts.append(contract)
        if kind == "OWNER_PAYLOAD":
            semantic_owner = OWNER_OVERRIDES.get(schema_id, owner)
            native = schema_id in {
                "stored_event",
                "commit_receipt",
                "aggregate_head_receipt",
            }
            static = schema_id.endswith("_registry") or schema_id.endswith("_profile")
            object_owner_entries.append(
                {
                    "object_schema_id": schema_id,
                    "object_schema_version": SCHEMA_VERSION,
                    "unique_semantic_owner": semantic_owner,
                    "precommit_writer": (
                        "NONE"
                        if native or static
                        else "WRITE_ONCE_WORK_ARCHIVE"
                    ),
                    "accepted_persistence_owner": (
                        "VERSIONED_CONTRACT_REPOSITORY"
                        if static
                        else "UNIT_OF_WORK"
                    ),
                    "acceptance_mode": (
                        "PREACCEPTED_STATIC"
                        if static
                        else (
                            "UOW_NATIVE_COMMIT_OUTPUT"
                            if native
                            else "UOW_ACCEPT_BY_EXACT_DIGEST"
                        )
                    ),
                }
            )
    manifest: dict[str, Any] = {
        "manifest_id": "THEORY_AGENT_V2_CANONICAL_CONTRACT_MANIFEST",
        "manifest_version": SCHEMA_VERSION,
        "implementation_contract_sha256": IMPLEMENTATION_CONTRACT_SHA256,
        "historical_architecture_schema_baseline_count": 118,
        "removed_schema_ids": sorted(REMOVED_SCHEMAS),
        "resolved_schema_identity_count_diagnostic_only": len(schema_entries),
        "schema_contracts": schema_contracts,
        "schema_registry": {
            "registry_id": "THEORY_AGENT_V2_SCHEMA_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "canonicalization_policy": "UTF8_JSON_JCS_RFC8785_SHA256_SUBSET_NO_FLOAT",
            "entries": schema_entries,
            "closed": True,
        },
        "object_owner_registry": {
            "registry_id": "THEORY_AGENT_V2_OBJECT_OWNER_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "entries": object_owner_entries,
            "closed": True,
        },
        "closed_error_registry": {
            "registry_id": "THEORY_AGENT_V2_CLOSED_ERROR_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "entries": _error_entries(),
            "closed": True,
        },
        "closed_event_registry": {
            "registry_id": "THEORY_AGENT_V2_CLOSED_EVENT_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "entries": _event_entries(),
            "closed": True,
        },
        "constraint_registry": {
            "registry_id": "THEORY_AGENT_V2_CONSTRAINT_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "entries": _constraint_entries(),
            "closed": True,
        },
        "plugin_policy_registry": {
            "registry_id": "THEORY_AGENT_V2_PLUGIN_POLICY_REGISTRY",
            "registry_version": SCHEMA_VERSION,
            "plugin_types": list(PLUGIN_TYPES),
            "entries": [],
            "required_plugin_ids": [],
            "optional_plugin_ids": [],
            "default_failure_policy": "RETURN_UNKNOWN",
            "dynamic_operations": "FORBIDDEN",
            "environment_permissions": {
                "network": "DENIED",
                "filesystem": "DENIED",
                "process": "DENIED",
                "environment": "DENIED",
                "ambient_clock": "DENIED",
                "randomness": "DENIED",
            },
            "closed": True,
        },
        "closed_enums": {
            key: list(values) for key, values in sorted(CLOSED_ENUMS.items())
        },
        "reducer_transition_tables": _transition_tables(),
        "event_name_resolution": {
            "coexistence_policy": (
                "WORK_ARTIFACT_AND_DOMAIN_TRANSITION_NAMES_MAY_COEXIST_ONLY_"
                "WHEN_TRIGGER_CLASS_AND_PAYLOAD_DIFFER"
            ),
            "unit_of_work_committed_phase": "POST_COMMIT_NOTIFICATION",
            "same_batch_commit_receipt_reference": "FORBIDDEN",
        },
        "authority_tuple": {
            "system_mode": SYSTEM_MODE,
            "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
            "executable": False,
            "paper_action_authority": "NONE",
            "live_action_authority": "NONE",
        },
        "manifest_digest": "",
    }
    # Freeze every nested registry before freezing the outer manifest.
    for registry_name in (
        "schema_registry",
        "object_owner_registry",
        "closed_error_registry",
        "closed_event_registry",
        "constraint_registry",
        "plugin_policy_registry",
    ):
        registry = manifest[registry_name]
        registry["registry_digest"] = canonical_digest(registry)
    return self_digest(manifest, "manifest_digest")


def schema_documents_from_manifest(
    manifest: Mapping[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    for entry in manifest["schema_registry"]["entries"]:
        document = schema_document(entry)
        if canonical_digest(document) != entry["schema_bytes_digest"]:
            raise ValueError(f"schema digest mismatch: {entry['schema_id']}")
        yield str(entry["schema_id"]), document


def validate_catalog_manifest(manifest: Mapping[str, Any]) -> None:
    verify_self_digest(manifest, "manifest_digest")
    entries = manifest["schema_registry"]["entries"]
    schema_ids = [entry["schema_id"] for entry in entries]
    if len(schema_ids) != len(set(schema_ids)):
        raise ValueError("duplicate schema identity")
    if set(schema_ids) != set(resolved_schema_owners()):
        raise ValueError("schema identity set mismatch")
    if "stage_activation_receipt" in schema_ids:
        raise ValueError("removed stage activation schema present")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["manifest_digest"]):
        raise ValueError("manifest digest lexical failure")
    for registry_name in (
        "schema_registry",
        "object_owner_registry",
        "closed_error_registry",
        "closed_event_registry",
        "constraint_registry",
        "plugin_policy_registry",
    ):
        registry = manifest[registry_name]
        supplied = registry.get("registry_digest")
        unsigned = dict(registry)
        unsigned.pop("registry_digest", None)
        if supplied != canonical_digest(unsigned):
            raise ValueError(f"nested registry digest mismatch: {registry_name}")
    for entry in entries:
        required_fields = list(entry["required_fields"])
        if len(required_fields) != len(set(required_fields)):
            raise ValueError(f"duplicate required field: {entry['schema_id']}")
        document = schema_document(entry)
        if document.get("additionalProperties") is not False:
            raise ValueError(f"open schema forbidden: {entry['schema_id']}")
        if canonical_digest(document) != entry["schema_bytes_digest"]:
            raise ValueError(f"schema bytes digest mismatch: {entry['schema_id']}")
    owner_payload_ids = {
        entry["schema_id"]
        for entry in entries
        if entry["schema_kind"] == "OWNER_PAYLOAD"
    }
    registered_owner_ids = {
        entry["object_schema_id"]
        for entry in manifest["object_owner_registry"]["entries"]
    }
    if registered_owner_ids != owner_payload_ids:
        raise ValueError("object owner registry identity mismatch")
    for enum_name, values in manifest["closed_enums"].items():
        if not values or len(values) != len(set(values)):
            raise ValueError(f"closed enum invalid: {enum_name}")
    error_codes = [
        entry["error_code"] for entry in manifest["closed_error_registry"]["entries"]
    ]
    if len(error_codes) != len(set(error_codes)):
        raise ValueError("duplicate error code")
    event_types = [
        entry["event_type"] for entry in manifest["closed_event_registry"]["entries"]
    ]
    if len(event_types) != len(set(event_types)):
        raise ValueError("duplicate event type")
    for event in manifest["closed_event_registry"]["entries"]:
        if event["payload_schema_id"] not in set(schema_ids):
            raise ValueError(
                f"event payload schema missing: {event['event_type']}"
            )
        if (
            event["event_type"] == "UNIT_OF_WORK_COMMITTED"
            and (
                event["trigger_class"] != "POST_COMMIT_NOTIFICATION"
                or event["same_batch_commit_receipt_reference"] is not False
            )
        ):
            raise ValueError("unit of work committed phase is cyclic")
    constraint_ids = [
        entry["constraint_id"]
        for entry in manifest["constraint_registry"]["entries"]
    ]
    if len(constraint_ids) != len(set(constraint_ids)):
        raise ValueError("duplicate constraint id")
    plugin_registry = manifest["plugin_policy_registry"]
    if (
        plugin_registry["entries"]
        or plugin_registry["required_plugin_ids"]
        or plugin_registry["optional_plugin_ids"]
    ):
        raise ValueError("E0 plugin registry must be empty")
    if manifest["authority_tuple"] != {
        "system_mode": SYSTEM_MODE,
        "external_execution_authority": EXTERNAL_EXECUTION_AUTHORITY,
        "executable": False,
        "paper_action_authority": "NONE",
        "live_action_authority": "NONE",
    }:
        raise ValueError("E0 authority tuple mismatch")
