from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from trade_system.theory_paper_v2.domain.market_cycle.evidence import (
    COLD,
    CORE_4,
    DELTA,
    EVENT_FAST,
    EVIDENCE_STATUSES,
    INCREMENT_NOT_DEMONSTRATED,
    KNOWN_FAIL,
    KNOWN_PASS,
    KNOWN_SOURCE_INSUFFICIENT,
    NEEDS_SEPARATE_AUTHORITY,
    POSITION_POLICY_DIMENSIONS,
    PREDICTION_ARMS,
    PREDICTION_PHASES,
    PUBLIC_DIRECT,
    SOURCE_INSUFFICIENT,
    SOURCE_UNOBSERVABLE,
    TARGET_NOT_MET,
    UNKNOWN_INCONCLUSIVE,
    UNOBSERVABLE,
    V332_EVIDENCE_POLICY_ID,
    CoverageComponentSummary,
    CoverageCycleSummary,
    EvidenceContractError,
    EvidencePolicy,
    PositionPairSummary,
    PredictionArmSummary,
    PredictionCycleSummary,
    SpeedCycleSummary,
    assess_coverage_readiness,
    assess_position_readiness,
    assess_prediction_readiness,
    assess_speed_readiness,
)
from trade_system.theory_paper_v2.domain.market_cycle.theory import (
    THEORY_REVISION,
    V332_THEORY_REVISION,
)


class MarketCycleEvidenceContractTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.policy = EvidencePolicy()

    def _speed(
        self,
        cycle_id: str,
        ordinal: int,
        *,
        analysis_profile: str = COLD,
        expected: int = 2,
        elapsed: int | None = 100,
        terminal_status: str | None = "PLAN_SEALED",
        failure_stage: str | None = None,
    ) -> SpeedCycleSummary:
        return SpeedCycleSummary(
            cycle_id=cycle_id,
            cohort_id=f"cohort-{analysis_profile.lower()}",
            analysis_profile=analysis_profile,
            attempt_ordinal=ordinal,
            expected_attempts=expected,
            elapsed_seconds=elapsed,
            terminal_status=terminal_status,
            failure_stage=failure_stage,
            data_profile="BASELINE_PRICE",
            environment_identity="runtime:model:transport:hardware:v1",
            theory_revision=THEORY_REVISION,
            source_done_elapsed_seconds=min(1, elapsed) if elapsed is not None else 1,
            deterministic_preparation_done_elapsed_seconds=(
                min(2, elapsed) if elapsed is not None else 2
            ),
            agent_done_elapsed_seconds=min(3, elapsed) if elapsed is not None else 3,
            position_and_selection_done_elapsed_seconds=(
                min(4, elapsed) if elapsed is not None else 4
            ),
            request_count=4,
            agent_round_trips=1,
            packet_size_bytes=4096,
        )

    def _component(
        self,
        component_id: str,
        *,
        source: str = PUBLIC_DIRECT,
        raw_saved: bool | None = True,
        missing_reason: str | None = None,
    ) -> CoverageComponentSummary:
        return CoverageComponentSummary(
            component_id=component_id,
            source_classification=source,
            scheduled=True,
            requested=True,
            responded=True if raw_saved is not None else None,
            raw_saved=raw_saved,
            parsed=True if raw_saved is True else raw_saved,
            admitted=True if raw_saved is True else raw_saved,
            fresh=True if raw_saved is True else raw_saved,
            replayable=True if raw_saved is True else raw_saved,
            missing_reason=missing_reason,
        )

    def _coverage_cycle(
        self,
        cycle_id: str,
        window_id: str,
        start: str,
        end: str,
        *,
        ordinal: int = 1,
        expected: int = 1,
        components: tuple[CoverageComponentSummary, ...] | None = None,
    ) -> CoverageCycleSummary:
        return CoverageCycleSummary(
            cycle_id=cycle_id,
            window_id=window_id,
            window_start_at=start,
            window_end_at=end,
            cycle_ordinal=ordinal,
            expected_cycles=expected,
            coverage_scope_id="OKX:BTC-USDT-SWAP:BASELINE_PRICE:15m",
            venue_id="OKX",
            instrument_id="BTC-USDT-SWAP",
            analysis_profile=COLD,
            data_profile="BASELINE_PRICE",
            theory_revision=THEORY_REVISION,
            terminal=True,
            failure_stage=None,
            pit_violation=False,
            instrument_identity_valid=True,
            closed_bar_valid=True,
            components=(
                tuple(self._component(component) for component in CORE_4)
                if components is None
                else components
            ),
        )

    def _two_windows(
        self,
        *,
        first_components: tuple[CoverageComponentSummary, ...] | None = None,
        second_components: tuple[CoverageComponentSummary, ...] | None = None,
        second_start: str = "2026-08-08T00:00:00+00:00",
        second_end: str = "2026-08-15T00:00:00+00:00",
    ) -> tuple[CoverageCycleSummary, CoverageCycleSummary]:
        return (
            self._coverage_cycle(
                "coverage-1",
                "window-1",
                "2026-08-01T00:00:00+00:00",
                "2026-08-08T00:00:00+00:00",
                components=first_components,
            ),
            self._coverage_cycle(
                "coverage-2",
                "window-2",
                second_start,
                second_end,
                components=second_components,
            ),
        )

    def _prediction_pair(
        self,
        cycle_id: str,
        phase: str,
        window_id: str,
        start: str,
        end: str,
        *,
        outcome: str | None = "UP",
        candidate_action: str = "LONG",
        price_action: str = "WAIT",
    ) -> PredictionCycleSummary:
        actions = {
            "V330_CANDIDATE": candidate_action,
            "PRICE_ONLY_DETERMINISTIC": price_action,
            "ALWAYS_LONG": "LONG",
            "ALWAYS_SHORT": "SHORT",
            "WAIT_ONLY": "WAIT",
        }
        return PredictionCycleSummary(
            cycle_id=cycle_id,
            phase=phase,
            window_id=window_id,
            window_start_at=start,
            window_end_at=end,
            pair_ordinal=1,
            expected_pairs=1,
            pit_snapshot_ref=f"snapshot:{cycle_id}",
            instrument_id="BTC-USDT-SWAP",
            analysis_profile=COLD,
            data_profile="BASELINE_PRICE",
            theory_revision=THEORY_REVISION,
            horizon_seconds=3600,
            outcome_definition_id="OKX_MARK_PRICE_UP_DOWN_FLAT_V1",
            decision_at=start,
            outcome_available_at=end if outcome is not None else None,
            outcome=outcome,
            eligible=True,
            arms=tuple(
                PredictionArmSummary(
                    arm_id=arm_id,
                    policy_id=f"{arm_id}:frozen-v1",
                    action=actions[arm_id],
                    sealed_at=start,
                )
                for arm_id in PREDICTION_ARMS
            ),
        )

    def _prediction_windows(
        self,
        *,
        calibration_outcome: str | None = "UP",
        confirmation_outcome: str | None = "UP",
        calibration_candidate_action: str = "LONG",
        confirmation_candidate_action: str = "LONG",
        calibration_price_action: str = "WAIT",
        confirmation_price_action: str = "WAIT",
    ) -> tuple[PredictionCycleSummary, PredictionCycleSummary]:
        return (
            self._prediction_pair(
                "prediction-calibration",
                "CALIBRATION",
                "prediction-window-calibration",
                "2026-08-01T00:00:00+00:00",
                "2026-08-08T00:00:00+00:00",
                outcome=calibration_outcome,
                candidate_action=calibration_candidate_action,
                price_action=calibration_price_action,
            ),
            self._prediction_pair(
                "prediction-confirmation",
                "UNTOUCHED_CONFIRMATION",
                "prediction-window-confirmation",
                "2026-08-08T00:00:00+00:00",
                "2026-08-15T00:00:00+00:00",
                outcome=confirmation_outcome,
                candidate_action=confirmation_candidate_action,
                price_action=confirmation_price_action,
            ),
        )

    def _position_pair(
        self,
        dimension: str,
        phase: str,
        *,
        candidate_score: int | None = 2,
        path_ref: str | None = "path:shared-future",
    ) -> PositionPairSummary:
        calibration = phase == "CALIBRATION"
        return PositionPairSummary(
            cycle_id=f"position-{dimension.lower()}-{phase.lower()}",
            dimension=dimension,
            phase=phase,
            window_id=(
                "position-window-calibration"
                if calibration
                else "position-window-confirmation"
            ),
            window_start_at=(
                "2026-08-01T00:00:00+00:00"
                if calibration
                else "2026-08-08T00:00:00+00:00"
            ),
            window_end_at=(
                "2026-08-08T00:00:00+00:00"
                if calibration
                else "2026-08-15T00:00:00+00:00"
            ),
            pair_ordinal=1,
            expected_pairs=1,
            changed_dimensions=(dimension,),
            forecast_ref="forecast:shared",
            path_ref=path_ref,
            baseline_policy_id=f"baseline:{dimension}",
            candidate_policy_id=f"candidate:{dimension}",
            baseline_reference_score=1,
            candidate_reference_score=candidate_score,
            baseline_guardrail_breached=False,
            candidate_guardrail_breached=False,
            authority="PUBLIC_REFERENCE_ONLY",
            theory_revision=THEORY_REVISION,
        )

    def test_policy_freezes_four_gates_and_only_allowed_statuses(self) -> None:
        self.assertEqual(self.policy.cold_budget_seconds, 900)
        self.assertEqual(self.policy.delta_budget_seconds, 120)
        self.assertIsNone(self.policy.event_fast_budget_seconds)
        self.assertEqual(self.policy.coverage_core_components, CORE_4)
        self.assertEqual(self.policy.coverage_required_window_count, 2)
        self.assertEqual(self.policy.coverage_window_seconds, 604800)
        self.assertEqual(self.policy.prediction_arms, PREDICTION_ARMS)
        self.assertEqual(
            PREDICTION_ARMS,
            (
                "V330_CANDIDATE",
                "PRICE_ONLY_DETERMINISTIC",
                "ALWAYS_LONG",
                "ALWAYS_SHORT",
                "WAIT_ONLY",
            ),
        )
        self.assertEqual(
            self.policy.prediction_phases,
            ("CALIBRATION", "UNTOUCHED_CONFIRMATION"),
        )
        self.assertEqual(self.policy.prediction_phases, PREDICTION_PHASES)
        self.assertEqual(self.policy.position_dimensions, POSITION_POLICY_DIMENSIONS)
        self.assertEqual(self.policy.position_phases, PREDICTION_PHASES)
        self.assertEqual(len(set(self.policy.position_dimensions)), 4)
        self.assertEqual(
            self.policy.position_execution_status, NEEDS_SEPARATE_AUTHORITY
        )
        self.assertEqual(
            EVIDENCE_STATUSES,
            {
                UNKNOWN_INCONCLUSIVE,
                KNOWN_PASS,
                KNOWN_FAIL,
                KNOWN_SOURCE_INSUFFICIENT,
                UNOBSERVABLE,
                INCREMENT_NOT_DEMONSTRATED,
                TARGET_NOT_MET,
                NEEDS_SEPARATE_AUTHORITY,
            },
        )
        with self.assertRaises(FrozenInstanceError):
            self.policy.cold_budget_seconds = 1
        with self.assertRaises(EvidenceContractError):
            EvidencePolicy(delta_budget_seconds=121)

    def test_v332_policy_requires_explicit_revision_bound_identity(self) -> None:
        policy = EvidencePolicy(
            policy_id=V332_EVIDENCE_POLICY_ID,
            theory_revision=V332_THEORY_REVISION,
        )

        self.assertEqual(V332_THEORY_REVISION, policy.theory_revision)
        self.assertEqual(V332_EVIDENCE_POLICY_ID, policy.policy_id)
        with self.assertRaisesRegex(EvidenceContractError, "identity"):
            EvidencePolicy(theory_revision=V332_THEORY_REVISION)

    def test_speed_pass_uses_frozen_cold_and_delta_targets(self) -> None:
        cold = assess_speed_readiness(
            self.policy,
            (
                self._speed("cold-1", 1, elapsed=899),
                self._speed("cold-2", 2, elapsed=900),
            ),
            analysis_profile=COLD,
        )
        self.assertEqual(cold.status, KNOWN_PASS)
        self.assertEqual((cold.denominator, cold.p50_seconds, cold.p95_seconds), (2, 899, 900))

        delta = assess_speed_readiness(
            self.policy,
            (
                self._speed("delta-1", 1, analysis_profile=DELTA, elapsed=119),
                self._speed("delta-2", 2, analysis_profile=DELTA, elapsed=120),
            ),
            analysis_profile=DELTA,
        )
        self.assertEqual(delta.status, KNOWN_PASS)
        self.assertEqual(delta.budget_seconds, 120)

    def test_speed_keeps_failures_in_denominator_and_missing_unknown(self) -> None:
        failed = assess_speed_readiness(
            self.policy,
            (
                self._speed("speed-1", 1, elapsed=100),
                self._speed(
                    "speed-2",
                    2,
                    elapsed=900,
                    terminal_status="INPUT_INVALID",
                    failure_stage="INPUT",
                ),
            ),
            analysis_profile=COLD,
        )
        self.assertEqual(failed.status, TARGET_NOT_MET)
        self.assertEqual((failed.denominator, failed.sealed_count, failed.failed_count), (2, 1, 1))

        missing = assess_speed_readiness(
            self.policy,
            (
                self._speed("missing-1", 1, elapsed=100),
                self._speed("missing-2", 2, elapsed=None),
            ),
            analysis_profile=COLD,
        )
        self.assertEqual(missing.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("ELAPSED_TIME_MISSING", missing.reasons)

    def test_event_fast_remains_unknown_without_a_frozen_budget(self) -> None:
        result = assess_speed_readiness(
            self.policy,
            (
                self._speed(
                    "event-1",
                    1,
                    analysis_profile=EVENT_FAST,
                    expected=1,
                    elapsed=10,
                ),
            ),
            analysis_profile=EVENT_FAST,
        )
        self.assertEqual(result.status, UNKNOWN_INCONCLUSIVE)
        self.assertIsNone(result.budget_seconds)
        self.assertEqual(result.p95_seconds, 10)
        self.assertIn("EVENT_FAST_BUDGET_NOT_FROZEN", result.reasons)

    def test_total_speed_without_stage_timing_or_scale_stays_unknown(self) -> None:
        incomplete = replace(
            self._speed("speed-incomplete", 1, expected=1, elapsed=100),
            packet_size_bytes=None,
        )
        result = assess_speed_readiness(
            self.policy,
            (incomplete,),
            analysis_profile=COLD,
        )
        self.assertEqual(result.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("STAGE_TIMING_OR_SCALE_MISSING", result.reasons)

    def test_coverage_pass_requires_two_complete_nonoverlapping_seven_day_windows(self) -> None:
        result = assess_coverage_readiness(self.policy, self._two_windows())
        self.assertEqual(result.status, KNOWN_PASS)
        self.assertEqual(result.denominator, 2)
        self.assertEqual(result.terminal_count, 2)
        self.assertEqual(result.usable_core4_count, 2)
        self.assertEqual(result.window_count, 2)

        one_window = assess_coverage_readiness(
            self.policy, (self._two_windows()[0],)
        )
        self.assertEqual(one_window.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("TWO_COVERAGE_WINDOWS_REQUIRED", one_window.reasons)

        overlap = assess_coverage_readiness(
            self.policy,
            self._two_windows(
                second_start="2026-08-07T00:00:00+00:00",
                second_end="2026-08-14T00:00:00+00:00",
            ),
        )
        self.assertEqual(overlap.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("COVERAGE_WINDOWS_OVERLAP", overlap.reasons)

    def test_coverage_explicit_failure_is_known_but_absent_data_stays_unknown(self) -> None:
        failed_components = tuple(
            self._component(
                component,
                raw_saved=False,
                missing_reason="CAPTURE_FAILED",
            )
            if component == "MARK_PRICE"
            else self._component(component)
            for component in CORE_4
        )
        failed = assess_coverage_readiness(
            self.policy,
            self._two_windows(first_components=failed_components),
        )
        self.assertEqual(failed.status, KNOWN_FAIL)
        self.assertEqual((failed.denominator, failed.failed_cycle_count), (2, 1))

        missing_components = tuple(
            self._component(component)
            for component in CORE_4
            if component != "MARK_PRICE"
        )
        missing = assess_coverage_readiness(
            self.policy,
            self._two_windows(first_components=missing_components),
        )
        self.assertEqual(missing.status, UNKNOWN_INCONCLUSIVE)
        self.assertTrue(
            any(reason.startswith("CORE_COMPONENT_SUMMARY_MISSING") for reason in missing.reasons)
        )

    def test_coverage_distinguishes_source_insufficient_and_unobservable(self) -> None:
        insufficient = tuple(
            self._component(component, source=SOURCE_INSUFFICIENT)
            if component == "MARK_PRICE"
            else self._component(component)
            for component in CORE_4
        )
        insufficient_result = assess_coverage_readiness(
            self.policy,
            self._two_windows(first_components=insufficient),
        )
        self.assertEqual(insufficient_result.status, KNOWN_SOURCE_INSUFFICIENT)

        unobservable = tuple(
            self._component(component, source=SOURCE_UNOBSERVABLE)
            if component == "MARK_PRICE"
            else self._component(component)
            for component in CORE_4
        )
        unobservable_result = assess_coverage_readiness(
            self.policy,
            self._two_windows(first_components=unobservable),
        )
        self.assertEqual(unobservable_result.status, UNOBSERVABLE)

    def test_prediction_requires_same_pit_five_arms_and_untouched_confirmation(self) -> None:
        result = assess_prediction_readiness(
            self.policy,
            self._prediction_windows(),
        )
        self.assertEqual(result.status, KNOWN_PASS)
        self.assertEqual((result.denominator, result.resolved_pairs), (2, 2))
        self.assertEqual(result.calibration_candidate_loss, 0)
        self.assertEqual(result.calibration_price_only_loss, 1)
        self.assertEqual(result.confirmation_candidate_loss, 0)
        self.assertEqual(result.confirmation_price_only_loss, 1)

        with self.assertRaises(EvidenceContractError):
            replace(
                self._prediction_windows()[0],
                arms=self._prediction_windows()[0].arms[:-1],
            )

    def test_prediction_missing_future_is_unknown_and_no_increment_is_explicit(self) -> None:
        missing = assess_prediction_readiness(
            self.policy,
            self._prediction_windows(confirmation_outcome=None),
        )
        self.assertEqual(missing.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("PAIRED_FUTURE_OUTCOME_MISSING", missing.reasons)

        not_demonstrated = assess_prediction_readiness(
            self.policy,
            self._prediction_windows(
                calibration_candidate_action="WAIT",
                confirmation_candidate_action="WAIT",
                calibration_price_action="LONG",
                confirmation_price_action="LONG",
            ),
        )
        self.assertEqual(
            not_demonstrated.status, INCREMENT_NOT_DEMONSTRATED
        )

    def test_position_requires_all_four_single_dimension_reference_pairs(self) -> None:
        pairs = tuple(
            self._position_pair(dimension, phase)
            for dimension in POSITION_POLICY_DIMENSIONS
            for phase in PREDICTION_PHASES
        )
        result = assess_position_readiness(self.policy, pairs)
        self.assertEqual(result.status, KNOWN_PASS)
        self.assertEqual(result.denominator, 8)
        self.assertEqual(result.covered_dimensions, POSITION_POLICY_DIMENSIONS)
        self.assertEqual(result.execution_status, NEEDS_SEPARATE_AUTHORITY)

        missing_path = assess_position_readiness(
            self.policy,
            (replace(pairs[0], path_ref=None), *pairs[1:]),
        )
        self.assertEqual(missing_path.status, UNKNOWN_INCONCLUSIVE)
        self.assertEqual(
            missing_path.execution_status, NEEDS_SEPARATE_AUTHORITY
        )

        missing_phase = assess_position_readiness(self.policy, pairs[:-1])
        self.assertEqual(missing_phase.status, UNKNOWN_INCONCLUSIVE)
        self.assertTrue(
            any(reason.startswith("POSITION_PHASE_MISSING") for reason in missing_phase.reasons)
        )

        missing_phase_field = assess_position_readiness(
            self.policy,
            (replace(pairs[0], phase=None), *pairs[1:]),
        )
        self.assertEqual(missing_phase_field.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn(
            "POSITION_PAIR_METADATA_MISSING", missing_phase_field.reasons
        )

        missing_window_field = assess_position_readiness(
            self.policy,
            (replace(pairs[0], window_start_at=None), *pairs[1:]),
        )
        self.assertEqual(missing_window_field.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn(
            "POSITION_PAIR_METADATA_MISSING", missing_window_field.reasons
        )

        incomplete_phase = assess_position_readiness(
            self.policy,
            (replace(pairs[0], expected_pairs=2), *pairs[1:]),
        )
        self.assertEqual(incomplete_phase.status, UNKNOWN_INCONCLUSIVE)
        self.assertTrue(
            any(
                reason.startswith("POSITION_PHASE_PAIRS_INCOMPLETE")
                for reason in incomplete_phase.reasons
            )
        )

        overlapping = assess_position_readiness(
            self.policy,
            (
                pairs[0],
                replace(
                    pairs[1],
                    window_start_at="2026-08-07T00:00:00+00:00",
                    window_end_at="2026-08-14T00:00:00+00:00",
                ),
                *pairs[2:],
            ),
        )
        self.assertEqual(overlapping.status, UNKNOWN_INCONCLUSIVE)
        self.assertTrue(
            any(
                reason.startswith("POSITION_CONFIRMATION_NOT_UNTOUCHED")
                for reason in overlapping.reasons
            )
        )

        policy_drift = assess_position_readiness(
            self.policy,
            (
                pairs[0],
                replace(pairs[1], candidate_policy_id="candidate:changed-after-calibration"),
                *pairs[2:],
            ),
        )
        self.assertEqual(policy_drift.status, UNKNOWN_INCONCLUSIVE)
        self.assertIn("POSITION_POLICY_ID_DRIFT", policy_drift.reasons)

    def test_position_no_reference_increment_never_becomes_execution_evidence(self) -> None:
        pairs = tuple(
            self._position_pair(
                dimension,
                phase,
                candidate_score=(
                    1
                    if dimension == "REENTRY"
                    and phase == "UNTOUCHED_CONFIRMATION"
                    else 2
                ),
            )
            for dimension in POSITION_POLICY_DIMENSIONS
            for phase in PREDICTION_PHASES
        )
        result = assess_position_readiness(self.policy, pairs)
        self.assertEqual(result.status, INCREMENT_NOT_DEMONSTRATED)
        self.assertEqual(result.execution_status, NEEDS_SEPARATE_AUTHORITY)

        otherwise_improved = tuple(
            self._position_pair(dimension, phase)
            for dimension in POSITION_POLICY_DIMENSIONS
            for phase in PREDICTION_PHASES
        )
        guardrail_worse = assess_position_readiness(
            self.policy,
            (
                replace(
                    otherwise_improved[0],
                    candidate_guardrail_breached=True,
                ),
                *otherwise_improved[1:],
            ),
        )
        self.assertEqual(
            guardrail_worse.status, INCREMENT_NOT_DEMONSTRATED
        )
        self.assertEqual(
            guardrail_worse.execution_status, NEEDS_SEPARATE_AUTHORITY
        )
        with self.assertRaises(EvidenceContractError):
            replace(
                pairs[0],
                changed_dimensions=("PROFIT_MANAGEMENT", "DYNAMIC_STOP"),
            )

    def test_float_elapsed_and_non_boolean_coverage_are_rejected(self) -> None:
        with self.assertRaises(EvidenceContractError):
            self._speed("float-speed", 1, expected=1, elapsed=1.5)
        with self.assertRaises(EvidenceContractError):
            CoverageComponentSummary(
                component_id="MARK_PRICE",
                source_classification=PUBLIC_DIRECT,
                scheduled=1,
                requested=True,
                responded=True,
                raw_saved=True,
                parsed=True,
                admitted=True,
                fresh=True,
                replayable=True,
            )


if __name__ == "__main__":
    unittest.main()
