from __future__ import annotations

from copy import deepcopy
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.governance.v32_experiment_contract import (
    DIGEST_FIELD,
    OUTCOME_HORIZONS_SECONDS,
    PILOT_NAME,
    SUPPORT_BINDING_KEYS,
    TOTAL_ANALYSIS_CYCLES,
    TOTAL_OUTCOME_SCHEDULES,
    V32ExperimentContractError,
    build_v32_experiment_contract_v1,
    verify_v32_experiment_contract_v1,
)


def _supports() -> dict[str, str]:
    return {
        key: format(index + 1, "x") * 64
        for index, key in enumerate(SUPPORT_BINDING_KEYS)
    }


def _contract() -> dict:
    return build_v32_experiment_contract_v1(
        contract_id="v32-pilot-contract",
        run_id="v32-pilot-run-not-authorized",
        frozen_at="2026-08-07T04:00:00Z",
        theory_relative_ref="theory/current/V3_2_DYNAMIC_AGGRESSIVE.md",
        theory_physical_sha256="f" * 64,
        theory_semantic_digest="9" * 64,
        support_bindings=_supports(),
    )


class V32ExperimentContractTests(unittest.TestCase):
    def test_exact_process_pilot_and_zero_execution_authority(self) -> None:
        contract = _contract()
        self.assertEqual(contract[DIGEST_FIELD], verify_v32_experiment_contract_v1(contract))
        self.assertEqual(PILOT_NAME, contract["pilot_name"])
        protocol = contract["pilot_protocol"]
        self.assertEqual(TOTAL_ANALYSIS_CYCLES, protocol["analysis_cycles"])
        self.assertEqual(list(OUTCOME_HORIZONS_SECONDS), protocol["outcome_horizons_seconds"])
        self.assertEqual(TOTAL_OUTCOME_SCHEDULES, protocol["scheduled_outcomes"])
        self.assertEqual("FULL_CONTEXT", protocol["cycle_1_mode"])
        self.assertEqual("DELTA_UPDATE", protocol["cycle_2_to_16_mode"])
        for field in (
            "executable",
            "account_access",
            "paper_trading",
            "live_trading",
            "order_submission",
            "credential_use",
            "funds_access",
            "portfolio_mutation",
            "fill_claim",
            "pnl_claim",
        ):
            self.assertIs(contract["authority_boundary"][field], False)

    def test_denominator_trap_is_frozen_out_before_relative_allocation(self) -> None:
        risk = _contract()["risk_policy"]
        self.assertEqual(
            "FIXED_ENVELOPE_TIMES_MIN_SUBJECTIVE_TIER_AND_RESIDUAL_"
            "THEN_PATH_NON_INFLATION_CAP_AFTER_TYPED_HARD_GATES",
            risk["effective_budget_method"],
        )
        self.assertEqual(
            "CAP_ONLY_HIGH_NEVER_AMPLIFIES_OBJECTIVE_CAP",
            risk["subjective_tier_cap_policy"],
        )
        self.assertEqual(
            "MAX_CLUSTER_TIER_NEVER_SUM",
            risk["same_direction_support_formula"],
        )
        self.assertEqual("MAX_TIER_NEVER_SUM", risk["opposed_direction_support_combination"])
        self.assertEqual(
            "DETERMINISTIC_COMPLETE_OR_INCOMPLETE_DIAGNOSTIC_ONLY_NO_RISK_SCALAR",
            risk["hypothesis_evidence_chain_coverage_policy"],
        )
        self.assertEqual(
            "UNKNOWN_NOT_IN_DYNAMIC_STATE",
            risk["source_admission_coverage_status"],
        )
        self.assertTrue(risk["agent_authored_numeric_quality_forbidden"])
        self.assertEqual(
            "REPLAYABLE_DIAGNOSTICS_AND_TYPED_HARD_FEASIBILITY_GATES_"
            "NO_COVERAGE_REGIME_LIQUIDITY_GEOMETRY_OR_COST_SCALAR",
            risk["objective_quality_policy"],
        )
        self.assertEqual(
            "INITIAL_HIGH_OR_LOW_TO_HIGH_REQUIRES_TWO_FRESH_MECHANISM_"
            "DISTINCT_REFS_AND_DIRECTIONAL_COUNTER_EVIDENCE",
            risk["high_tier_evidence_policy"],
        )
        self.assertEqual(
            "PRESERVE_FULL_CLOSURE_IGNORE_ONLY_SHARED_VENUE_PROJECTION_"
            "FOR_PAIRING_REQUIRE_DISJOINT_OTHER_MATERIAL_DEPENDENCIES_"
            "DIFFERENT_REQUEST_AND_DIRECTIONAL_OBSERVABLE_FAMILY_"
            "NOT_STATISTICAL_INDEPENDENCE",
            risk["mechanism_distinct_evidence_policy"],
        )
        self.assertEqual(
            {
                "PRICE_ACTION",
                "POSITIONING",
                "FUNDING_CROWDING",
                "ORDERBOOK_LIQUIDITY",
                "TRADE_FLOW",
            },
            set(risk["directional_observable_families"]),
        )
        self.assertEqual(
            {"PROVIDER_METADATA", "CONTRACT_SPEC"},
            set(risk["nondirectional_metadata_families"]),
        )
        self.assertTrue(
            {"TICKER", "MARK_PRICE", "CLOSED_CANDLES_15M"}.issubset(
                risk["price_action_components"]
            )
        )
        self.assertEqual(
            "ENTER_NONDIRECTIONAL_ONE_FRESH_HARD_REF_ALLOWED_"
            "NONDIRECTIONAL_TO_DIRECTION_REQUIRES_TWO_FRESH_MECHANISM_"
            "DISTINCT_REFS_OR_TWO_CONSECUTIVE_MACHINE_VERIFIED_CLOSED_15M_BARS",
            risk["regime_transition_policy"],
        )
        self.assertEqual(
            "NEUTRAL_CHOPPY_VOLATILITY_WITHOUT_DIRECTION_TRANSITION_OTHER_"
            "UNKNOWN_BLOCK_DIRECTIONAL_NEW_RISK_ZERO_CURRENT_BUDGET_"
            "RISK_CANDIDATES_REMAIN_UNTRIGGERED_CONDITIONAL_PLANS_BOUND_ONLY_"
            "TO_TYPED_BREAKOUT_BOUNDARIES_NO_ORDER_SUBMISSION_RANGE_MAY_"
            "RETAIN_CONDITIONAL_MEAN_REVERSION_PATHS",
            _contract()["action_policy"]["nondirectional_regime_policy"],
        )
        trigger = _contract()["action_policy"][
            "nondirectional_research_breakout_trigger_policy"
        ]
        self.assertEqual(
            "DOMAIN_FROM_SEALED_CANDIDATES_AND_ZONES",
            trigger["derivation_owner"],
        )
        self.assertFalse(
            trigger["agent_supplied_threshold_or_comparator_allowed"]
        )
        self.assertEqual("CLOSED_CANDLES_15M", trigger["source_component_id"])
        self.assertTrue(trigger["closed_bar_required"])
        self.assertEqual(
            1, trigger["required_consecutive_closed_bars_for_reanalysis"]
        )
        self.assertEqual(
            "RESEARCH_REANALYSIS_ONLY_NO_AUTOMATIC_ACTION_OR_RISK",
            trigger["match_effect"],
        )
        self.assertFalse(trigger["continuous_monitor_implemented"])
        self.assertEqual("NONE", trigger["order_or_oco_claim"])
        self.assertFalse(trigger["executable"])
        lineage = _contract()["action_policy"][
            "reference_tranche_lineage_policy"
        ]
        self.assertFalse(lineage["genesis_active_parent_allowed"])
        self.assertTrue(lineage["risk_plan_promotes_exact_selected_tranche"])
        self.assertTrue(lineage["hold_or_reduce_carries_exact_parent"])
        self.assertTrue(lineage["close_retires_parent"])
        self.assertTrue(
            lineage[
                "add_parent_id_direction_entry_and_stop_exact_echo_required"
            ]
        )
        self.assertTrue(
            lineage[
                "failure_refs_must_be_fresh_typed_contradiction_or_active_invalidation"
            ]
        )
        self.assertTrue(
            lineage[
                "generic_source_support_renewal_tier_or_zone_ref_cannot_prove_failure"
            ]
        )
        self.assertTrue(
            lineage[
                "new_add_or_reverse_tranche_id_must_differ_from_parent"
            ]
        )
        self.assertTrue(lineage["expired_parent_must_retire_before_next_plan"])
        self.assertFalse(
            lineage["agent_parent_rotation_or_geometry_rewrite_allowed"]
        )
        self.assertEqual("0", risk["minimum_forced_risk"])
        self.assertEqual(
            "MAX_ACTIONABLE_MEMBER_TIER_NO_SUM",
            risk["dependency_cluster_aggregation"],
        )

    def test_objective_reference_risk_inputs_are_frozen_outside_agent_control(
        self,
    ) -> None:
        risk = _contract()["risk_policy"]
        self.assertEqual(
            "FIXED_ONE_USDT_STRESS_REFERENCE_NO_ACCOUNT_OR_EXECUTION_CLAIM",
            risk["mode"],
        )
        self.assertEqual("NON_ACCOUNT_RESEARCH_STRESS_USDT", risk["reference_risk_unit"])
        policy = risk[
            "objective_reference_risk_input_policy"
        ]
        self.assertEqual("contract-value", policy["contract_value_datum_id"])
        self.assertEqual(
            "contract-multiplier", policy["contract_multiplier_datum_id"]
        )
        self.assertEqual("price-tick", policy["price_tick_datum_id"])
        self.assertEqual("quantity-step", policy["quantity_step_datum_id"])
        self.assertEqual(
            "minimum-quantity", policy["minimum_quantity_datum_id"]
        )
        self.assertEqual(
            "CONTRACT_VALUE_TIMES_CONTRACT_MULTIPLIER",
            policy["multiplier_reference_derivation"],
        )
        self.assertEqual(
            {
                "fee_stress_reference": "0.002",
                "slippage_stress_reference": "0.001",
                "funding_bound_reference": "0.001",
                "tail_gap_reference": "0.005",
            },
            policy["frozen_non_account_research_stress_policy"]["rates"],
        )
        self.assertEqual(
            "FROZEN_NON_ACCOUNT_RESEARCH_STRESS_NOT_ACTUAL_FEE_OR_FILL_OR_MAX_LOSS",
            policy["frozen_non_account_research_stress_policy"][
                "policy_label"
            ],
        )
        self.assertEqual(
            "USDT_PER_CONTRACT",
            policy["frozen_non_account_research_stress_policy"][
                "stress_reference_unit"
            ],
        )
        self.assertEqual(
            {
                "actual_account_fee_tier": "UNKNOWN_NOT_ACCESSED",
                "actual_slippage": "UNKNOWN_NOT_OBSERVED",
                "actual_tail_max_loss": "UNKNOWN_NOT_DEFINED",
            },
            policy["frozen_non_account_research_stress_policy"][
                "unknown_retention"
            ],
        )
        self.assertEqual(
            "SEPARATE_AUTHORIZATION_AND_QUALIFICATION_REQUIRED",
            policy["frozen_non_account_research_stress_policy"][
                "future_account_or_execution_adapter_policy"
            ],
        )
        self.assertTrue(policy["agent_override_forbidden"])

        tampered = deepcopy(_contract())
        tampered["risk_policy"]["objective_reference_risk_input_policy"][
            "frozen_non_account_research_stress_policy"
        ]["rates"]["fee_stress_reference"] = "0.003"
        tampered = self_digest(tampered, DIGEST_FIELD)
        with self.assertRaisesRegex(
            V32ExperimentContractError, "RECONSTRUCTION_MISMATCH"
        ):
            verify_v32_experiment_contract_v1(tampered)

    def test_opposite_candidates_do_not_force_positive_weight_or_trade(self) -> None:
        contract = _contract()
        self.assertEqual(
            ["EXTREME_UNCERTAINTY", "LOW", "HIGH"],
            contract["hypothesis_policy"]["subjective_plausibility_tiers"],
        )
        self.assertEqual(
            8, contract["inactivity_policy"]["review_after_consecutive_cycles"]
        )
        self.assertEqual(
            7200, contract["inactivity_policy"]["review_after_seconds"]
        )
        self.assertTrue(
            contract["inactivity_policy"][
                "current_pilot_thresholds_agent_override_forbidden"
            ]
        )
        reentry = contract["action_policy"]["reentry_budget_policy"]
        self.assertEqual(86400, reentry["rolling_window_seconds"])
        self.assertEqual("2", reentry["max_cumulative_reference_risk"])
        self.assertEqual(
            "FIXED_ONE_NON_ACCOUNT_RESEARCH_STRESS_USDT_PER_COUNTED_"
            "ATTEMPT_ENVELOPE_TWO_ATTEMPT_CUMULATIVE_CAP_NO_AGENT_OVERRIDE",
            reentry["current_pilot_budget_policy"],
        )
        self.assertEqual(
            "NON_ACCOUNT_RESEARCH_STRESS_USDT",
            reentry["max_cumulative_reference_risk_unit"],
        )
        self.assertEqual(2, reentry["max_attempts"])
        self.assertTrue(reentry["exhausted_remains_locked_after_cooldown_expiry"])
        self.assertEqual("ONE_GLOBAL_CHURN_BREAKER_PER_INSTRUMENT", reentry["scope"])
        self.assertTrue(reentry["reset_before_original_window_expiry_forbidden"])
        self.assertEqual(
            ["OPEN_PROBE", "REVERSE"],
            reentry["same_direction_risk_aliases_require_normalization"],
        )
        self.assertEqual(
            ["OPEN_PROBE", "REENTER", "REVERSE"],
            reentry["active_ledger_counted_action_kinds"],
        )
        self.assertFalse(reentry["initial_inactive_open_probe_counts"])
        self.assertTrue(reentry["initial_probe_arms_single_use_lock"])
        self.assertEqual(
            "INITIAL_PROBE_USED", reentry["initial_probe_lock_status"]
        )
        self.assertEqual(86400, reentry["initial_probe_lock_window_seconds"])
        self.assertTrue(
            reentry["second_unfailed_initial_probe_cannot_be_free"]
        )
        self.assertTrue(
            reentry["initial_probe_lock_allows_counted_open_or_reverse"]
        )
        self.assertTrue(
            reentry["initial_stop_counts_toward_consecutive_failure_breaker"]
        )
        self.assertEqual(2, reentry["max_consecutive_stop_failures"])
        self.assertEqual(
            {
                "attempts_used": 0,
                "consecutive_failures": 1,
                "cumulative_reference_risk": "0",
            },
            reentry["initial_exit_available_counters"],
        )
        self.assertTrue(reentry["opposite_direction_aliases_are_not_free"])
        self.assertEqual(
            "ANY_DIRECTION_SAME_INSTRUMENT",
            reentry["active_ledger_direction_scope"],
        )
        self.assertEqual(
            "REENTER", reentry["canonical_same_direction_action_kind"]
        )
        escape = contract["action_policy"]["future_physical_escape_contract"]
        self.assertEqual(
            "NOT_IMPLEMENTED_NOT_QUALIFIED", escape["implementation_status"]
        )
        self.assertTrue(escape["separate_authority_required"])
        self.assertFalse(
            escape["research_recovery_supervisor_is_execution_risk_supervisor"]
        )
        self.assertEqual(8, len(escape["activation_gates"]))
        self.assertIn(
            "COUNTED_ACTIVE_LEDGER_INSTRUMENT_CHURN_ACTION_OPEN_PROBE_"
            "REENTER_OR_REVERSE",
            reentry["consecutive_failure_transition"],
        )
        self.assertIn("NOT_FILL_OR_POSITION", reentry["current_pilot_attempt_basis"])
        self.assertEqual(
            "CANDIDATE_COMPLETENESS_ONLY_EXTREME_UNCERTAINTY_OR_BLOCKED_ALLOWED",
            contract["hypothesis_policy"]["directional_opposition"],
        )
        self.assertFalse(contract["inactivity_policy"]["forced_trade_or_minimum_exposure"])
        self.assertFalse(contract["action_policy"]["wait_is_costless_default"])
        self.assertEqual(
            [
                "OPEN_PROBE",
                "ADD",
                "HOLD",
                "REDUCE",
                "CLOSE",
                "REENTER",
                "REVERSE",
                "WAIT",
            ],
            contract["action_policy"]["legal_research_actions"],
        )
        self.assertTrue(
            contract["action_policy"][
                "partial_harvest_is_management_event_not_independent_action"
            ]
        )
        self.assertTrue(
            contract["action_policy"]["hold_is_distinct_from_flat_wait"]
        )

    def test_expiry_modifier_and_stop_not_fill_are_explicit(self) -> None:
        contract = _contract()
        hypothesis = contract["hypothesis_policy"]
        self.assertTrue(hypothesis["timestamp_only_renewal_forbidden"])
        self.assertIn("ACTION_THESIS", hypothesis["ttl_seconds_by_type"])
        modifier = contract["zone_and_modifier_policy"]
        self.assertTrue(modifier["modifier_global_broadcast_forbidden"])
        self.assertTrue(modifier["shared_zone_or_dependency_required"])
        self.assertEqual(
            {"ATTENTION_MOMENTUM_FEEDBACK", "OTHER", "UNKNOWN"},
            set(modifier["modifier_types"])
            - {
                "FALSE_BREAK_STOP_RUN",
                "LIQUIDITY_VACUUM",
                "FORCED_LIQUIDATION_CASCADE",
                "CROSS_VENUE_DISLOCATION",
                "VENUE_OR_NETWORK_DISRUPTION",
                "EVENT_SHOCK",
            },
        )
        outcome = contract["outcome_policy"]
        self.assertEqual(900, outcome["outcome_grace_seconds"])
        self.assertEqual(
            "metric:okx-public-mark-price-usdt", outcome["observable"]
        )
        self.assertEqual(
            "FIRST_SHARED_PUBLIC_MARK_TICK_AT_OR_AFTER_HORIZON_WITHIN_GRACE",
            outcome["observation_semantics"],
        )
        self.assertFalse(outcome["stop_or_limit_touched_is_fill"])
        self.assertTrue(outcome["position_or_pnl_output_forbidden"])

    def test_support_binding_set_and_digests_are_exact(self) -> None:
        supports = _supports()
        supports["unexpected"] = "0" * 64
        with self.assertRaisesRegex(
            V32ExperimentContractError, "SUPPORT_BINDINGS_INVALID"
        ):
            build_v32_experiment_contract_v1(
                contract_id="v32-pilot-contract",
                run_id="run",
                frozen_at="2026-08-07T04:00:00Z",
                theory_relative_ref="theory.md",
                theory_physical_sha256="f" * 64,
                theory_semantic_digest="9" * 64,
                support_bindings=supports,
            )

    def test_authorized_revision_and_post_boundary_audit_are_frozen(self) -> None:
        contract = _contract()
        revision = contract["authorized_revision_policy"]
        self.assertEqual(
            [
                "DETERMINISTIC_DEDUPLICATION",
                "TYPED_COMPACTION",
                "DEPENDENCY_CLOSURE_SHARDING",
                "ALL_NECESSARY_SHARDS",
            ],
            revision["context_capacity_order"],
        )
        self.assertTrue(revision["arbitrary_top_k_or_semantic_omission_forbidden"])
        self.assertTrue(revision["objective_unknown_preserved"])
        self.assertFalse(revision["subjective_unknown_assessment_is_probability"])
        self.assertTrue(revision["manual_public_evidence_is_future_only_no_backfill"])
        self.assertTrue(revision["authorized_revision_cycle_registry_required"])
        self.assertEqual(
            "POST_CORRESPONDING_TYPED_BOUNDARY",
            revision["cycle_audit_narrative_stage"],
        )
        self.assertEqual(
            "POST_ACCEPTANCE_ONLY", revision["acceptance_narrative_stage"]
        )
        self.assertTrue(
            revision["cycle_audit_completion_required_before_next_cycle_permit"]
        )
        self.assertEqual(
            {
                "authorized_revision_support_bundle_digest",
                "recovery_supervision_policy_digest",
                "workspace_freeze_receipt_digest",
            },
            {
                revision["support_bundle_digest_key"],
                revision["recovery_supervision_policy_digest_key"],
                revision["workspace_freeze_receipt_digest_key"],
            },
        )
        supports = _supports()
        supports[SUPPORT_BINDING_KEYS[0]] = "not-a-digest"
        with self.assertRaisesRegex(V32ExperimentContractError, "SUPPORT_BINDING_INVALID"):
            build_v32_experiment_contract_v1(
                contract_id="v32-pilot-contract",
                run_id="run",
                frozen_at="2026-08-07T04:00:00Z",
                theory_relative_ref="theory.md",
                theory_physical_sha256="f" * 64,
                theory_semantic_digest="9" * 64,
                support_bindings=supports,
            )

    def test_semantic_tampering_cannot_be_self_digest_laundered(self) -> None:
        contract = deepcopy(_contract())
        contract["risk_policy"]["single_weight_10_max_fraction_of_upper_bound"] = "1"
        contract = self_digest(contract, DIGEST_FIELD)
        with self.assertRaisesRegex(V32ExperimentContractError, "RECONSTRUCTION_MISMATCH"):
            verify_v32_experiment_contract_v1(contract)

    def test_frozen_time_must_be_canonical_utc(self) -> None:
        with self.assertRaisesRegex(V32ExperimentContractError, "FROZEN_AT_INVALID"):
            build_v32_experiment_contract_v1(
                contract_id="v32-pilot-contract",
                run_id="run",
                frozen_at="2026-08-07T12:00:00+08:00",
                theory_relative_ref="theory.md",
                theory_physical_sha256="f" * 64,
                theory_semantic_digest="9" * 64,
                support_bindings=_supports(),
            )


if __name__ == "__main__":
    unittest.main()
