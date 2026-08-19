from __future__ import annotations

import unittest
from dataclasses import replace

from trade_system.theory_paper_v2.application.scenarios import (
    CANONICAL_SCENARIOS,
    DATASET_TYPE,
    INDEPENDENT_COHORT,
    SNDK_COHORT,
    PredicateOutcome,
    ScenarioValidationStatus,
    canonical_scenario_registry_digest,
    run_canonical_scenario,
    run_canonical_scenarios,
    validate_canonical_scenario_registry,
)


EXPECTED_TITLES = (
    "trend continuation after rebound",
    "rebound failure",
    "false breakout",
    "range",
    "deep pullback and recovery",
    "no-pullback acceleration",
    "event gap through stop",
    "initial stage fails immediately",
    "confirmation stage triggers and reverses",
    "trend stage becomes forward-RR ineligible after appreciation",
    "target and stop touched in one bar",
    "missed wake with an intermediate trigger and reversal",
    "geometry replacement ACK race",
    "CORE exit with surviving thesis and reentry obligation",
    "continuation reentry without preferred pullback",
    "supervised to unattended transition",
    "unattended stale data or lost protection",
    "tactical signal attempting strategic invalidation",
    "feasible non-no-action candidates with repeated Agent no-action selection",
    "missing required Agent role or bootstrap state",
    "expired cross-timescale lease with a fast-layer strategic mutation attempt",
    "recursive feasibility FAIL and UNKNOWN after an otherwise attractive add",
    "conditional future branch submitted without current-data reapproval",
    "coherent forecasts without calibration or probability-use authorization",
    "suspected/confirmed regime shift attempting to invalidate or trade",
    "aggregate revision match with state-digest mismatch, and the converse",
    "lagging projection or snapshot used as a command head",
    "frozen feasible opportunity comparator versus a hindsight-only comparator",
    "forged stage receipt attempting to create a fill or quantity",
    "nonempty E0 calibration registry or probability-authorization instance",
    "unanimous Agent output attempting to erase PIT/data/path uncertainty",
    "atomic strategic exit-to-reentry commit with one deliberately failed effect",
)


class CanonicalScenarioHarnessTests(unittest.TestCase):
    def test_registry_is_exact_contract_section_19_2(self) -> None:
        validate_canonical_scenario_registry()

        self.assertEqual(
            tuple(item.scenario_id for item in CANONICAL_SCENARIOS),
            tuple(f"S19_2_{index:02d}" for index in range(1, 33)),
        )
        self.assertEqual(
            tuple(item.ordinal for item in CANONICAL_SCENARIOS),
            tuple(range(1, 33)),
        )
        self.assertEqual(
            tuple(item.title for item in CANONICAL_SCENARIOS),
            EXPECTED_TITLES,
        )
        self.assertEqual(len(CANONICAL_SCENARIOS), 32)

    def test_every_scenario_declares_a_real_predicate_and_explicit_expectation(
        self,
    ) -> None:
        for definition in CANONICAL_SCENARIOS:
            with self.subTest(definition.scenario_id):
                self.assertTrue(definition.predicate_id)
                self.assertIn(":", definition.predicate_id)
                self.assertTrue(definition.expected_code)
                self.assertIsInstance(
                    definition.expected_outcome, PredicateOutcome
                )
                self.assertTrue(callable(definition.executor))
                self.assertEqual(definition.dataset_type, DATASET_TYPE)

        self.assertNotIn(
            "all_pass",
            " ".join(
                definition.predicate_id.lower()
                for definition in CANONICAL_SCENARIOS
            ),
        )

    def test_registry_has_independent_non_sndk_cohort(self) -> None:
        cohorts = {item.cohort_id for item in CANONICAL_SCENARIOS}
        self.assertIn(SNDK_COHORT, cohorts)
        self.assertIn(INDEPENDENT_COHORT, cohorts)
        self.assertGreater(
            sum(
                item.cohort_id == INDEPENDENT_COHORT
                for item in CANONICAL_SCENARIOS
            ),
            0,
        )
        self.assertLess(
            sum(item.cohort_id == SNDK_COHORT for item in CANONICAL_SCENARIOS),
            len(CANONICAL_SCENARIOS),
        )

    def test_full_harness_matches_all_frozen_expectations(self) -> None:
        report = run_canonical_scenarios()

        self.assertEqual(report.pass_count, 32)
        self.assertEqual(report.fail_count, 0)
        self.assertEqual(report.unknown_count, 0)
        self.assertEqual(len(report.results), 32)
        self.assertEqual(
            report.contract_section,
            "THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0:19.2",
        )
        for definition, result in zip(
            CANONICAL_SCENARIOS, report.results, strict=True
        ):
            with self.subTest(result.scenario_id):
                self.assertEqual(
                    result.status, ScenarioValidationStatus.PASS
                )
                self.assertEqual(
                    result.observed_outcome, definition.expected_outcome
                )
                self.assertEqual(
                    result.observed_code, definition.expected_code
                )
                self.assertTrue(result.evidence_digest)
                self.assertTrue(result.result_digest)

    def test_expected_domain_unknown_is_not_hidden_by_validation_status(
        self,
    ) -> None:
        report = run_canonical_scenarios()
        expected_unknown = {
            result.scenario_id: result
            for result in report.results
            if result.expected_outcome is PredicateOutcome.UNKNOWN
        }

        self.assertEqual(set(expected_unknown), {"S19_2_14", "S19_2_31"})
        for result in expected_unknown.values():
            self.assertEqual(result.observed_outcome, PredicateOutcome.UNKNOWN)
            self.assertEqual(result.status, ScenarioValidationStatus.PASS)

    def test_repeat_run_has_identical_registry_results_and_report_digest(
        self,
    ) -> None:
        first = run_canonical_scenarios()
        second = run_canonical_scenarios()

        self.assertEqual(
            canonical_scenario_registry_digest(), first.registry_digest
        )
        self.assertEqual(first.registry_digest, second.registry_digest)
        self.assertEqual(first.report_digest, second.report_digest)
        self.assertEqual(
            tuple(result.result_digest for result in first.results),
            tuple(result.result_digest for result in second.results),
        )
        self.assertEqual(
            tuple(result.evidence_digest for result in first.results),
            tuple(result.evidence_digest for result in second.results),
        )

    def test_per_scenario_result_can_report_fail_and_unknown(self) -> None:
        baseline = CANONICAL_SCENARIOS[0]
        failed = run_canonical_scenario(
            replace(baseline, expected_code="DELIBERATE_EXPECTATION_MISMATCH")
        )

        def raises_deterministically():
            raise RuntimeError("deterministic scenario boundary")

        unknown = run_canonical_scenario(
            replace(baseline, executor=raises_deterministically)
        )

        self.assertEqual(failed.status, ScenarioValidationStatus.FAIL)
        self.assertEqual(failed.observed_outcome, PredicateOutcome.APPLIED)
        self.assertEqual(unknown.status, ScenarioValidationStatus.UNKNOWN)
        self.assertEqual(unknown.observed_outcome, PredicateOutcome.UNKNOWN)
        self.assertEqual(
            unknown.observed_code, "SCENARIO_EXECUTION_EXCEPTION"
        )


if __name__ == "__main__":
    unittest.main()
