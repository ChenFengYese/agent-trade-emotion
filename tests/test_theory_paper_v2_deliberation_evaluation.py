from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trade_system.theory_paper_v2.domain.common import ReducerStatus
from trade_system.theory_paper_v2.domain.deliberation import (
    BLIND_REQUIRED_OMISSIONS,
    AtomicEffectType,
    CandidateDecisionMetrics,
    ChallengeCategory,
    ChallengeClaim,
    ChallengeDisposition,
    ChallengeEnvelope,
    ChallengeMode,
    ChallengeResult,
    ChallengeTerminalEffect,
    DecisionContext,
    DecisionCriterionPolicy,
    ProposedActionPlan,
    assemble_candidate_bundles,
    make_decision_criterion_policy,
    make_no_action_plan,
    select_by_frozen_policy,
    validate_challenge_boundary,
    validate_proposed_action_plan,
)
from trade_system.theory_paper_v2.domain.evaluation import (
    CalibrationRegistry,
    CoherenceVerdict,
    ContinuationBranch,
    CounterfactualTier,
    CoverageVerdict,
    DataStatus,
    DecimalInterval,
    FeasibilityStatus,
    ForecastCoherenceReceipt,
    ForecastIssuanceReceipt,
    ForecastOutcomeStatus,
    OpportunityStatus,
    OutcomeResolutionReceipt,
    PathKind,
    PathPayoffCell,
    ProbabilityStatus,
    ProbabilityUse,
    ProbabilityUseAuthorization,
    assess_recursive_feasibility,
    authorize_current_plan_action,
    authorize_probability_use,
    build_calibration_dataset_manifest,
    build_path_payoff_matrix,
    build_receding_horizon_plan,
    calculate_linear_pnl_interval,
    create_empty_e0_calibration_registry,
    issue_ex_ante_opportunity_cost,
    make_stress_scenario_set,
    validate_e0_calibration_registry,
)
from trade_system.theory_paper_v2.domain.governance import (
    REQUIRED_HARD_CONSTRAINT_IDS,
    ConstraintClass,
    ConstraintDecision,
    ConstraintEvaluation,
    ConstraintVerdict,
    assess_selection,
    build_feasible_action_set,
    evaluate_hard_constraints,
)
from trade_system.theory_paper_v2.domain.policy import (
    ActionIntent,
    GeometryOperation,
    ProtectiveActionType,
)


class DeliberationEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 31, 1, tzinfo=UTC)
        self.proposal_ref = "proposal:1"
        self.claim = ChallengeClaim(
            claim_id="claim:1",
            proposal_ref=self.proposal_ref,
            subject_object_refs=("context:1",),
            category=ChallengeCategory.OMITTED_COMPETING_PATH,
            requested_disposition=ChallengeResult.SOFT,
        )
        self.challenge = ChallengeEnvelope(
            challenge_id="challenge:1",
            challenge_mode=ChallengeMode.POST_PROPOSAL,
            proposal_ref=self.proposal_ref,
            reasoning_strategy_contract_ref="reasoning:challenger",
            role_context_view_ref="context-view:challenger",
            role_context_proposal_ref=self.proposal_ref,
            claims=(self.claim,),
        )
        self.disposition = ChallengeDisposition(
            disposition_id="disposition:1",
            proposal_ref=self.proposal_ref,
            challenge_ref=self.challenge.challenge_id,
            result=ChallengeResult.SOFT,
            verified_claim_refs=(),
            verified_constraint_or_invariant_refs=(),
            affected_proposed_plan_refs=(),
            terminal_effect=ChallengeTerminalEffect.NONE,
            deterministic_validator_version="1.0.0",
        )
        self.keep_plan = ProposedActionPlan(
            plan_id="plan:keep",
            strategic_episode_ref="episode:1",
            decision_cutoff=self.now,
            path_ref="path:trend",
            cross_timescale_control_envelope_ref="lease:1",
            strategic_delta_facet_ref="strategic:same",
            position_facet_ref="position:keep",
            action_intent=ActionIntent.KEEP_CORE,
            protective_action_type=ProtectiveActionType.NONE,
            geometry_operation=GeometryOperation.KEEP,
            atomic_effect_types=(),
            position_delta=Decimal("0"),
            risk_delta=Decimal("0"),
        )
        self.no_action_plan = make_no_action_plan(
            strategic_episode_ref="episode:1",
            decision_cutoff=self.now,
            path_ref="path:unknown",
            envelope_ref="lease:1",
            next_review_at=self.now + timedelta(hours=1),
            unmet_dependency_refs=("dependency:volume",),
        )

    def assemble(self, plans: tuple[ProposedActionPlan, ...] | None = None):
        return assemble_candidate_bundles(
            proposal_ref=self.proposal_ref,
            challenge=self.challenge,
            disposition=self.disposition,
            proposed_plans=plans or (self.keep_plan,),
            no_action_plan=self.no_action_plan,
            required_meaningful_plan_refs=frozenset(
                plan.plan_id for plan in (plans or (self.keep_plan,))
            ),
        )

    @staticmethod
    def all_pass_evaluations(candidate_set, evidence_ref: str):
        return {
            candidate.candidate_ref: {
                constraint_id: ConstraintEvaluation(
                    constraint_id=constraint_id,
                    verdict=ConstraintDecision.PASS,
                    evidence_or_calculation_refs=(evidence_ref,),
                )
                for constraint_id in REQUIRED_HARD_CONSTRAINT_IDS
            }
            for candidate in candidate_set.candidates
        }

    def feasible(self):
        candidate_set = self.assemble().value
        policy = self.policy()
        hard = evaluate_hard_constraints(
            candidate_set=candidate_set,
            evaluations_by_candidate=self.all_pass_evaluations(
                candidate_set, "evidence:all-pass"
            ),
            constraint_engine_version="1.0.0",
        ).value
        return build_feasible_action_set(
            candidate_set=candidate_set,
            hard_verdict_set=hard,
            decision_criterion_policy_ref=policy.policy_id,
            decision_criterion_policy_digest=policy.policy_digest,
        ).value

    def policy(self) -> DecisionCriterionPolicy:
        return make_decision_criterion_policy(
            policy_id="policy:1",
            revision=1,
            valid_from=self.now - timedelta(hours=1),
            valid_until=self.now + timedelta(days=1),
            tie_break_order=(
                "LOWER_WORST_CASE_LOSS",
                "LOWER_TAIL_LOSS",
                "LOWER_COST",
                "LOWER_TURNOVER",
                "EARLIER_OBLIGATION_REVIEW",
                "CANONICAL_ACTION_ID",
            ),
        )

    @staticmethod
    def interval(
        lower: str, upper: str, unit: str = "ACCOUNT_USD"
    ) -> DecimalInterval:
        return DecimalInterval(Decimal(lower), Decimal(upper), unit)

    def matrix(self, feasible=None):
        feasible = feasible or self.feasible()
        plan_refs = tuple(
            candidate.proposed_action_plan_ref
            for candidate in feasible.candidate_bundle_set.candidates
        )
        cells = tuple(
            PathPayoffCell(
                path=path,
                action_plan_ref=action_ref,
                account_pnl_interval=self.interval("-2", "4"),
                total_account_risk=self.interval("0", "2"),
                marginal_account_risk=self.interval("0", "1"),
                max_drawdown=self.interval("0", "2"),
                stress_loss=self.interval("0", "3"),
                tail_loss=self.interval("0", "4"),
                intermediate_state_refs=("state:1",),
                data_status=DataStatus.PARTIALLY_IDENTIFIED,
            )
            for path in (
                PathKind.FAILURE,
                PathKind.NORMAL_REBOUND,
                PathKind.TREND_CONTINUATION,
                PathKind.REBOUND_EXHAUSTION,
                PathKind.OTHER,
                PathKind.UNKNOWN,
            )
            for action_ref in plan_refs
        )
        return build_path_payoff_matrix(
            matrix_id="matrix:1",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            decision_horizon_ref="horizon:1",
            planning_context_id="planning:1",
            candidate_action_set_digest=(
                feasible.candidate_bundle_set.candidate_set_digest
            ),
            action_plan_refs=plan_refs,
            cells=cells,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
            ordinal_path_ranks=(
                (PathKind.FAILURE, 5),
                (PathKind.NORMAL_REBOUND, 2),
                (PathKind.TREND_CONTINUATION, 1),
                (PathKind.REBOUND_EXHAUSTION, 4),
                (PathKind.OTHER, 3),
            ),
        )

    def recursive(
        self,
        candidate_ref: str,
        *,
        coverage: CoverageVerdict = CoverageVerdict.PASS,
        continuations: dict[str, tuple[str, ...]] | None = None,
    ):
        stress = make_stress_scenario_set(
            scenario_set_id="stress:1",
            frozen_at=self.now,
            scenario_refs=("scenario:gap", "scenario:reverse"),
            required_scenario_class_refs=("class:gap", "class:reverse"),
            coverage_verdict=coverage,
        )
        return assess_recursive_feasibility(
            receipt_id=f"recursive:{candidate_ref}",
            candidate_action_ref=candidate_ref,
            decision_cutoff=self.now,
            starting_aggregate_head_refs=("head:episode", "head:position"),
            planning_horizon_ref="horizon:1",
            next_review_at=self.now + timedelta(hours=1),
            stress_scenario_set=stress,
            reachable_state_summary_refs=("reachable:1",),
            scenario_continuation_refs=continuations
            if continuations is not None
            else {
                "scenario:gap": ("action:terminal",),
                "scenario:reverse": ("action:reduce",),
            },
            terminal_safe_action_ref="action:terminal",
            hard_constraint_result_refs=("constraints:1",),
            solver_or_evaluator_version="1.0.0",
            solver_or_evaluator_digest="b" * 64,
        )

    def test_plan_facets_and_atomic_reentry_are_enforced(self) -> None:
        valid = validate_proposed_action_plan(self.keep_plan)
        self.assertEqual(ReducerStatus.APPLIED, valid.status)
        missing_reentry = replace(
            self.keep_plan,
            plan_id="plan:flat",
            action_intent=ActionIntent.EXIT_TO_REENTRY_PENDING,
            strategic_status="ACTIVE",
        )
        result = validate_proposed_action_plan(missing_reentry)
        self.assertEqual("REENTRY_CREATION_ATOMIC_EFFECT_REQUIRED", result.error.code)
        atomic = replace(
            missing_reentry,
            atomic_effect_types=(AtomicEffectType.CREATE_REENTRY_CONTRACT,),
        )
        self.assertEqual(
            ReducerStatus.APPLIED, validate_proposed_action_plan(atomic).status
        )
        wrong_owner = replace(
            self.keep_plan,
            plan_id="plan:wrong-effect",
            atomic_effect_types=(AtomicEffectType.CREATE_REENTRY_CONTRACT,),
        )
        self.assertEqual(
            "ACTION_FACET_INCOMPATIBLE",
            validate_proposed_action_plan(wrong_owner).error.code,
        )

    def test_hedge_and_authority_overreach_emit_no_candidate_set(self) -> None:
        hedge = replace(
            self.keep_plan,
            plan_id="plan:hedge",
            requested_lot_role="HEDGE",
        )
        result = self.assemble((self.keep_plan, hedge))
        self.assertEqual(ReducerStatus.REJECTED, result.status)
        self.assertEqual("CANDIDATE_HEDGE_FORBIDDEN_E0", result.error.code)
        overreach = replace(
            self.keep_plan,
            plan_id="plan:live",
            external_execution_authority="LIVE",
            executable=True,
        )
        result = self.assemble((overreach,))
        self.assertEqual("CANDIDATE_E0_AUTHORITY_OVERREACH", result.error.code)
        suffixed = replace(
            self.keep_plan,
            plan_id="plan:suffixed",
            action_intent="KEEP_CORE_E0",
        )
        self.assertEqual(
            "ACTION_INTENT_UNKNOWN",
            validate_proposed_action_plan(suffixed).error.code,
        )
        forged_fingerprint = replace(
            self.keep_plan,
            plan_id="plan:forged-fingerprint",
            semantic_fingerprint="0" * 64,
        )
        self.assertEqual(
            "PROPOSED_ACTION_SEMANTIC_FINGERPRINT_MISMATCH",
            self.assemble((forged_fingerprint,)).error.code,
        )
        fake_no_action = replace(
            self.no_action_plan,
            action_intent=ActionIntent.KEEP_CORE,
        )
        result = assemble_candidate_bundles(
            proposal_ref=self.proposal_ref,
            challenge=self.challenge,
            disposition=self.disposition,
            proposed_plans=(self.keep_plan,),
            no_action_plan=fake_no_action,
            required_meaningful_plan_refs=frozenset({self.keep_plan.plan_id}),
        )
        self.assertEqual("FEASIBLE_SET_NO_ACTION_MISSING", result.error.code)

    def test_blind_and_post_proposal_challenge_visibility_are_exact(self) -> None:
        self.assertEqual(
            ReducerStatus.APPLIED,
            validate_challenge_boundary(
                self.challenge, exact_proposal_ref=self.proposal_ref
            ).status,
        )
        blind_claim = replace(
            self.claim,
            claim_id="claim:blind",
            proposal_ref=None,
            claims_proposal_byte_defect=False,
        )
        blind = ChallengeEnvelope(
            challenge_id="challenge:blind",
            challenge_mode=ChallengeMode.BLIND_CONTEXT_ONLY,
            proposal_ref=None,
            reasoning_strategy_contract_ref="reasoning:blind",
            role_context_view_ref="context-view:blind",
            role_context_proposal_ref=None,
            claims=(blind_claim,),
            omitted_projection_classes=BLIND_REQUIRED_OMISSIONS,
            blinding_proof_ref="proof:blind",
        )
        self.assertEqual(
            ReducerStatus.APPLIED,
            validate_challenge_boundary(
                blind, exact_proposal_ref=self.proposal_ref
            ).status,
        )
        leaked = replace(blind, proposal_ref=self.proposal_ref)
        self.assertEqual(
            "BLIND_CHALLENGE_PROPOSAL_HIDDEN",
            validate_challenge_boundary(
                leaked, exact_proposal_ref=self.proposal_ref
            ).error.code,
        )
        unseen_defect = replace(
            blind,
            claims=(replace(blind_claim, claims_proposal_byte_defect=True),),
        )
        self.assertEqual(
            ReducerStatus.REJECTED,
            validate_challenge_boundary(
                unseen_defect, exact_proposal_ref=self.proposal_ref
            ).status,
        )

    def test_complete_hard_constraint_coverage_and_removal_semantics(self) -> None:
        self.assertEqual(33, len(REQUIRED_HARD_CONSTRAINT_IDS))
        candidate_set = self.assemble().value
        evaluations = self.all_pass_evaluations(candidate_set, "evidence:1")
        first_ref = next(
            candidate.candidate_ref
            for candidate in candidate_set.candidates
            if not candidate.is_no_action
        )
        missing = {
            candidate: dict(items)
            for candidate, items in evaluations.items()
        }
        missing[first_ref].pop(next(iter(REQUIRED_HARD_CONSTRAINT_IDS)))
        self.assertEqual(
            ReducerStatus.REJECTED,
            evaluate_hard_constraints(
                candidate_set=candidate_set,
                evaluations_by_candidate=missing,
                constraint_engine_version="1.0.0",
            ).status,
        )
        fail = {
            candidate: dict(items)
            for candidate, items in evaluations.items()
        }
        fail_id = next(iter(REQUIRED_HARD_CONSTRAINT_IDS))
        fail[first_ref][fail_id] = ConstraintEvaluation(
            constraint_id=fail_id,
            verdict=ConstraintDecision.FAIL,
            evidence_or_calculation_refs=("evidence:fail",),
        )
        hard = evaluate_hard_constraints(
            candidate_set=candidate_set,
            evaluations_by_candidate=fail,
            constraint_engine_version="1.0.0",
        ).value
        soft = ConstraintVerdict(
            verdict_ref="soft:1",
            candidate_ref=candidate_set.no_action_candidate_ref,
            constraint_id="diagnostic:warning",
            constraint_class=ConstraintClass.SOFT,
            verdict=ConstraintDecision.FAIL,
            failed_field_json_pointers=(),
            evidence_or_calculation_refs=("evidence:soft",),
            affected_candidate_ref=candidate_set.no_action_candidate_ref,
            protective_actions_remain_allowed=True,
            next_lawful_evidence_or_review_refs=(),
            verdict_digest="c" * 64,
        )
        feasible = build_feasible_action_set(
            candidate_set=candidate_set,
            hard_verdict_set=hard,
            decision_criterion_policy_ref="policy:1",
            decision_criterion_policy_digest=self.policy().policy_digest,
            soft_or_informational_verdicts=(soft,),
        ).value
        self.assertEqual((candidate_set.no_action_candidate_ref,), tuple(
            candidate.candidate_ref for candidate in feasible.feasible_candidates
        ))
        self.assertEqual(("soft:1",), feasible.retained_soft_verdict_refs)

    def test_hard_unknown_does_not_silently_become_safe_pass(self) -> None:
        candidate_set = self.assemble().value
        evaluations = self.all_pass_evaluations(candidate_set, "evidence:1")
        candidate_ref = candidate_set.candidates[0].candidate_ref
        constraint_id = next(iter(REQUIRED_HARD_CONSTRAINT_IDS))
        evaluations[candidate_ref][constraint_id] = ConstraintEvaluation(
            constraint_id=constraint_id,
            verdict=ConstraintDecision.UNKNOWN,
            evidence_or_calculation_refs=("missing:data",),
        )
        hard = evaluate_hard_constraints(
            candidate_set=candidate_set,
            evaluations_by_candidate=evaluations,
            constraint_engine_version="1.0.0",
        ).value
        result = build_feasible_action_set(
            candidate_set=candidate_set,
            hard_verdict_set=hard,
            decision_criterion_policy_ref="policy:1",
            decision_criterion_policy_digest=self.policy().policy_digest,
        )
        self.assertEqual(ReducerStatus.UNKNOWN, result.status)

    def test_selector_is_policy_bound_and_cannot_invent_candidate(self) -> None:
        feasible = self.feasible()
        policy = self.policy()
        context = DecisionContext(
            context_id="context:1",
            decision_cutoff=self.now,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
            decision_criterion_policy_ref=policy.policy_id,
            decision_criterion_policy_digest=policy.policy_digest,
        )
        metrics = tuple(
            CandidateDecisionMetrics(
                candidate_ref=candidate.candidate_ref,
                robust_dominated=False,
                minimax_regret=Decimal("0.2")
                if candidate.is_no_action
                else Decimal("0.1"),
                worst_case_loss=Decimal("0")
                if candidate.is_no_action
                else Decimal("1"),
                tail_loss=Decimal("0")
                if candidate.is_no_action
                else Decimal("1"),
                cost=Decimal("0"),
                turnover=Decimal("0"),
                obligation_review_at=self.now + timedelta(hours=1)
                if candidate.is_no_action
                else None,
            )
            for candidate in feasible.feasible_candidates
        )
        selected = select_by_frozen_policy(
            feasible_set=feasible,
            context=context,
            policy=policy,
            metrics=metrics,
        ).value
        self.assertNotEqual(
            feasible.no_action_candidate_ref, selected.selected_candidate_ref
        )
        outside = select_by_frozen_policy(
            feasible_set=feasible,
            context=context,
            policy=policy,
            metrics=metrics,
            requested_candidate_ref="candidate:invented",
        )
        self.assertEqual("SELECTOR_OUTSIDE_FEASIBLE_SET", outside.error.code)
        mismatched_context = replace(
            context, decision_criterion_policy_digest="f" * 64
        )
        self.assertEqual(
            "SELECTION_CRITERION_POLICY_MISMATCH",
            select_by_frozen_policy(
                feasible_set=feasible,
                context=mismatched_context,
                policy=policy,
                metrics=metrics,
            ).error.code,
        )

    def test_unknown_selection_forces_explicit_no_action_obligation(self) -> None:
        feasible = self.feasible()
        context = DecisionContext(
            context_id="context:unknown",
            decision_cutoff=self.now,
            probability_status=ProbabilityStatus.UNKNOWN,
            decision_criterion_policy_ref="policy:1",
            decision_criterion_policy_digest=self.policy().policy_digest,
        )
        metrics = tuple(
            CandidateDecisionMetrics(
                candidate_ref=candidate.candidate_ref,
                robust_dominated=False,
                minimax_regret=Decimal("0"),
                worst_case_loss=Decimal("0"),
                tail_loss=Decimal("0"),
                cost=Decimal("0"),
                turnover=Decimal("0"),
                obligation_review_at=(
                    self.now + timedelta(hours=1) if candidate.is_no_action else None
                ),
            )
            for candidate in feasible.feasible_candidates
        )
        result = select_by_frozen_policy(
            feasible_set=feasible,
            context=context,
            policy=self.policy(),
            metrics=metrics,
        ).value
        self.assertEqual(feasible.no_action_candidate_ref, result.selected_candidate_ref)
        self.assertTrue(result.no_action_despite_non_abstain_feasible)

    def test_decimal_payoff_and_matrix_are_deterministic_and_complete(self) -> None:
        pnl = calculate_linear_pnl_interval(
            side="LONG",
            entry_price=Decimal("100"),
            terminal_price=self.interval("109", "111", "PRICE"),
            quantity=Decimal("2"),
            fees=self.interval("1", "1"),
            slippage=self.interval("0.5", "1"),
            funding=self.interval("0", "0.5"),
            account_unit_ref="ACCOUNT_USD",
        )
        self.assertEqual(Decimal("15.5"), pnl.lower)
        self.assertEqual(Decimal("20.5"), pnl.upper)
        with self.assertRaises(ValueError):
            DecimalInterval(1.0, Decimal("2"), "ACCOUNT_USD")  # type: ignore[arg-type]
        matrix = self.matrix()
        self.assertEqual(ReducerStatus.APPLIED, matrix.status)
        self.assertIn((PathKind.OTHER, "plan:keep"), matrix.value.by_key())
        self.assertIn((PathKind.UNKNOWN, "plan:keep"), matrix.value.by_key())
        incomplete = replace(
            next(iter(matrix.value.cells)),
            action_plan_ref="plan:unregistered",
        )
        cells = (incomplete, *matrix.value.cells[1:])
        result = build_path_payoff_matrix(
            matrix_id="matrix:bad",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            decision_horizon_ref="horizon:1",
            planning_context_id="planning:1",
            candidate_action_set_digest="d" * 64,
            action_plan_refs=matrix.value.actions,
            cells=cells,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
        )
        self.assertEqual("PATH_PAYOFF_MATRIX_COVERAGE_INCOMPLETE", result.error.code)
        forged_cell = replace(matrix.value.cells[0], cell_digest="0" * 64)
        forged_cells = (forged_cell, *matrix.value.cells[1:])
        forged = build_path_payoff_matrix(
            matrix_id="matrix:forged",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            decision_horizon_ref="horizon:1",
            planning_context_id="planning:1",
            candidate_action_set_digest="d" * 64,
            action_plan_refs=matrix.value.actions,
            cells=forged_cells,
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
        )
        self.assertEqual("PATH_PAYOFF_CELL_DIGEST_MISMATCH", forged.error.code)

    def test_decision_policy_digest_is_not_agent_mutable(self) -> None:
        policy = self.policy()
        with self.assertRaisesRegex(
            ValueError, "DECISION_CRITERION_POLICY_INVALID"
        ):
            replace(policy, ordinal_mode_rule="AGENT_CHOSEN_OBJECTIVE")
        with self.assertRaisesRegex(
            ValueError, "DECISION_CRITERION_POLICY_INVALID"
        ):
            replace(policy, policy_digest="0" * 64)

    def test_probability_branches_fail_closed_in_e0(self) -> None:
        registry = create_empty_e0_calibration_registry(
            registry_id="calibration:e0",
            registry_version="1.0.0",
            valid_from=self.now,
        )
        self.assertEqual(
            ReducerStatus.APPLIED,
            authorize_probability_use(
                probability_status=ProbabilityStatus.ORDINAL_ONLY,
                requested_use=ProbabilityUse.ORDINAL_PATH_RANKING,
                registry=registry,
                authorization=None,
                coherence_receipt=None,
                decision_cutoff=self.now,
            ).status,
        )
        ev = authorize_probability_use(
            probability_status=ProbabilityStatus.ORDINAL_ONLY,
            requested_use=ProbabilityUse.EXPECTED_VALUE,
            registry=registry,
            authorization=None,
            coherence_receipt=None,
            decision_cutoff=self.now,
        )
        self.assertEqual("PROBABILITY_USE_UNAUTHORIZED_E0", ev.error.code)
        calibrated = authorize_probability_use(
            probability_status=ProbabilityStatus.CALIBRATED_OOS,
            requested_use=ProbabilityUse.CONDITIONAL_PAYOFF_COMPARISON,
            registry=registry,
            authorization=None,
            coherence_receipt=ForecastCoherenceReceipt(
                receipt_id="coherence:1",
                probability_status=ProbabilityStatus.CALIBRATED_OOS,
                status=CoherenceVerdict.PASS,
                other_path_present=True,
            ),
            decision_cutoff=self.now,
        )
        self.assertEqual(ReducerStatus.REJECTED, calibrated.status)
        nonempty = replace(registry, calibration_record_refs=("record:1",))
        self.assertEqual(
            ReducerStatus.REJECTED,
            validate_e0_calibration_registry(nonempty).status,
        )
        authorization = ProbabilityUseAuthorization(
            authorization_id="auth:1",
            calibration_record_ref="record:1",
            coherence_receipt_ref="coherence:1",
            allowed_uses=frozenset({"EXPECTED_VALUE"}),
            valid_from=self.now,
            valid_until=self.now + timedelta(hours=1),
        )
        self.assertEqual(
            ReducerStatus.REJECTED,
            authorize_probability_use(
                probability_status=ProbabilityStatus.ORDINAL_ONLY,
                requested_use=ProbabilityUse.ORDINAL_PATH_RANKING,
                registry=registry,
                authorization=authorization,
                coherence_receipt=None,
                decision_cutoff=self.now,
            ).status,
        )

    def test_calibration_lineage_is_one_to_one_and_point_in_time(self) -> None:
        issuance = ForecastIssuanceReceipt(
            forecast_issuance_id="forecast:1",
            forecaster_ref="forecaster:1",
            event_definition_ref="event:1",
            instrument_or_universe_scope_ref="instrument:1",
            forecast_horizon_ref="horizon:1",
            issued_at=self.now,
            available_at=self.now,
            probability_vector_ref="probability:untrusted",
            probability_status_at_issuance=ProbabilityStatus.ORDINAL_ONLY,
            calibration_record_ref=None,
            source_input_manifest_ref="source:1",
            source_input_digest="a" * 64,
            outcome_due_at=self.now + timedelta(hours=4),
        )
        outcome = OutcomeResolutionReceipt(
            outcome_resolution_id="outcome:1",
            forecast_issuance_ref=issuance.forecast_issuance_id,
            event_definition_ref=issuance.event_definition_ref,
            label_resolver_ref="resolver:1",
            outcome_status=ForecastOutcomeStatus.RESOLVED,
            resolved_label_ref="label:1",
            observation_window_start=self.now,
            observation_window_end=self.now + timedelta(hours=4),
            label_available_at=self.now + timedelta(hours=5),
            source_receipt_refs=("source:label",),
        )
        result = build_calibration_dataset_manifest(
            manifest_id="manifest:1",
            dataset_version="1.0.0",
            issuances=(issuance,),
            outcomes=(outcome,),
            training_cutoff=self.now,
            evaluation_cutoff=self.now + timedelta(hours=6),
            overlap_handling_policy_ref="overlap:1",
            cohort_and_regime_policy_ref="cohort:1",
            label_leakage_check_ref="leakage:1",
        )
        self.assertEqual(ReducerStatus.APPLIED, result.status)
        leaked = build_calibration_dataset_manifest(
            manifest_id="manifest:leaked",
            dataset_version="1.0.0",
            issuances=(issuance,),
            outcomes=(outcome,),
            training_cutoff=self.now,
            evaluation_cutoff=self.now + timedelta(hours=4, minutes=30),
            overlap_handling_policy_ref="overlap:1",
            cohort_and_regime_policy_ref="cohort:1",
            label_leakage_check_ref="leakage:1",
        )
        self.assertEqual("CALIBRATION_LABEL_LEAKAGE", leaked.error.code)

    def test_recursive_feasibility_and_future_branches_do_not_authorize_risk(self) -> None:
        feasible = self.feasible()
        selected_ref = next(
            candidate.candidate_ref
            for candidate in feasible.feasible_candidates
            if not candidate.is_no_action
        )
        recursive = self.recursive(selected_ref).value
        self.assertEqual(FeasibilityStatus.PASS, recursive.status)
        matrix = self.matrix(feasible).value
        branch = ContinuationBranch(
            branch_id="branch:future",
            trigger_predicate_refs=("predicate:future",),
            planned_action_ref="action:future",
            remaining_risk_budget_ref="risk:remaining",
            review_at=self.now + timedelta(hours=2),
        )
        plan = build_receding_horizon_plan(
            plan_id="rh:1",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            selected_candidate_ref=selected_ref,
            feasible_set=feasible,
            matrix=matrix,
            recursive_feasibility=recursive,
            continuation_branches=(branch,),
            planned_review_points=(self.now + timedelta(hours=1),),
            terminal_fallback_action_ref="action:terminal",
            cost_model_ref="cost:1",
        ).value
        self.assertEqual(
            ReducerStatus.APPLIED,
            authorize_current_plan_action(plan, selected_ref).status,
        )
        future = authorize_current_plan_action(plan, branch.planned_action_ref)
        self.assertEqual(
            "RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED", future.error.code
        )
        unknown = self.recursive(
            selected_ref, coverage=CoverageVerdict.UNKNOWN
        ).value
        self.assertEqual(FeasibilityStatus.UNKNOWN, unknown.status)

        add_plan = replace(
            self.keep_plan,
            plan_id="plan:add",
            action_intent=ActionIntent.ACTIVATE_REGISTERED_STAGE,
            registered_stage_ref="stage:1",
            requested_lot_role="TACTICAL",
            position_delta=Decimal("1"),
            risk_delta=Decimal("0.01"),
        )
        candidate_set = self.assemble((add_plan,)).value
        hard = evaluate_hard_constraints(
            candidate_set=candidate_set,
            evaluations_by_candidate=self.all_pass_evaluations(
                candidate_set, "evidence:pass"
            ),
            constraint_engine_version="1.0.0",
        ).value
        add_feasible = build_feasible_action_set(
            candidate_set=candidate_set,
            hard_verdict_set=hard,
            decision_criterion_policy_ref="policy:1",
            decision_criterion_policy_digest=self.policy().policy_digest,
        ).value
        add_ref = next(
            candidate.candidate_ref
            for candidate in add_feasible.feasible_candidates
            if candidate.introduces_new_risk
        )
        add_matrix = self.matrix(add_feasible).value
        unknown_add = self.recursive(
            add_ref, coverage=CoverageVerdict.UNKNOWN
        ).value
        result = build_receding_horizon_plan(
            plan_id="rh:add",
            strategic_episode_ref="episode:1",
            revision=1,
            decision_cutoff=self.now,
            selected_candidate_ref=add_ref,
            feasible_set=add_feasible,
            matrix=add_matrix,
            recursive_feasibility=unknown_add,
            continuation_branches=(),
            planned_review_points=(self.now + timedelta(hours=1),),
            terminal_fallback_action_ref="action:terminal",
            cost_model_ref="cost:1",
        )
        self.assertEqual("RECURSIVE_FEASIBILITY_NOT_PASS", result.error.code)

    def test_opportunity_cost_is_ex_ante_and_never_realized_loss(self) -> None:
        comparator = self.recursive("candidate:comparator").value
        issued = issue_ex_ante_opportunity_cost(
            receipt_id="opportunity:1",
            candidate_ref="candidate:evaluated",
            evaluated_action_ref="candidate:evaluated",
            comparator_action_ref="candidate:comparator",
            comparator_policy_ref="comparator-policy:1",
            comparator_policy_digest="f" * 64,
            comparator_frozen_at=self.now,
            decision_cutoff=self.now,
            comparator_feasibility=comparator,
            same_risk_and_authority_constraints=True,
            comparison_horizon_ref="horizon:1",
            path_complexity_or_switch_count=1,
            fill_slippage_and_fee_model_ref="cost:1",
            support_overlap_status="PASS",
            identification_contract_ref=None,
            counterfactual_tier=CounterfactualTier.MODEL_CONDITIONAL,
            evaluated_value_interval=self.interval("1", "3"),
            comparator_value_interval=self.interval("4", "8"),
            uncertainty_interval=self.interval("0", "2"),
            status=OpportunityStatus.PARTIALLY_IDENTIFIED,
            assumption_refs=("assumption:1",),
            calculator_contract_version="1.0.0",
        )
        self.assertEqual(ReducerStatus.APPLIED, issued.status)
        self.assertEqual(
            (Decimal("1"), Decimal("7")),
            (
                issued.value.conditional_difference_interval.lower,
                issued.value.conditional_difference_interval.upper,
            ),
        )
        self.assertTrue(issued.value.not_realized_loss)
        self.assertFalse(hasattr(issued.value, "realized_loss"))
        self.assertEqual(
            "DIAGNOSTIC_ONLY", issued.value.formal_metric_eligibility.value
        )
        hindsight = issue_ex_ante_opportunity_cost(
            receipt_id="opportunity:future",
            candidate_ref="candidate:evaluated",
            evaluated_action_ref="candidate:evaluated",
            comparator_action_ref="candidate:comparator",
            comparator_policy_ref="comparator-policy:1",
            comparator_policy_digest="f" * 64,
            comparator_frozen_at=self.now + timedelta(seconds=1),
            decision_cutoff=self.now,
            comparator_feasibility=comparator,
            same_risk_and_authority_constraints=True,
            comparison_horizon_ref="horizon:1",
            path_complexity_or_switch_count=1,
            fill_slippage_and_fee_model_ref="cost:1",
            support_overlap_status="PASS",
            identification_contract_ref=None,
            counterfactual_tier=CounterfactualTier.MODEL_CONDITIONAL,
            evaluated_value_interval=self.interval("1", "3"),
            comparator_value_interval=self.interval("4", "8"),
            uncertainty_interval=self.interval("0", "2"),
            status=OpportunityStatus.PARTIALLY_IDENTIFIED,
            assumption_refs=(),
            calculator_contract_version="1.0.0",
        )
        self.assertEqual("OPPORTUNITY_COMPARATOR_NOT_FROZEN", hindsight.error.code)

    def test_governance_accepts_only_exact_selected_member(self) -> None:
        feasible = self.feasible()
        policy = self.policy()
        context = DecisionContext(
            context_id="context:1",
            decision_cutoff=self.now,
            probability_status=ProbabilityStatus.UNKNOWN,
            decision_criterion_policy_ref=policy.policy_id,
            decision_criterion_policy_digest=policy.policy_digest,
        )
        metrics = tuple(
            CandidateDecisionMetrics(
                candidate_ref=item.candidate_ref,
                robust_dominated=False,
                minimax_regret=Decimal("0"),
                worst_case_loss=Decimal("0"),
                tail_loss=Decimal("0"),
                cost=Decimal("0"),
                turnover=Decimal("0"),
                obligation_review_at=(
                    self.now + timedelta(hours=1) if item.is_no_action else None
                ),
            )
            for item in feasible.feasible_candidates
        )
        selection = select_by_frozen_policy(
            feasible_set=feasible,
            context=context,
            policy=policy,
            metrics=metrics,
        ).value
        assessment = assess_selection(
            selection=selection,
            feasible_set=feasible,
            challenge_disposition_ref=self.disposition.disposition_id,
            expected_head_ref="head:1",
            schema_pit_state_verdict_refs=("pit:pass",),
            hard_constraint_verdict_refs=("constraints:pass",),
        )
        self.assertEqual(ReducerStatus.APPLIED, assessment.status)
        forged = replace(selection, selected_candidate_ref="candidate:forged")
        self.assertEqual(
            ReducerStatus.REJECTED,
            assess_selection(
                selection=forged,
                feasible_set=feasible,
                challenge_disposition_ref=self.disposition.disposition_id,
                expected_head_ref="head:1",
                schema_pit_state_verdict_refs=("pit:pass",),
                hard_constraint_verdict_refs=("constraints:pass",),
            ).status,
        )


if __name__ == "__main__":
    unittest.main()
