import copy
import unittest

from trade_system.g2_evaluator import AblationPair, FeatureTerm, G2EvaluationError, G2EvaluatorPolicy, evaluate_g2
from trade_system.types import parse_utc


class G2EvaluatorTests(unittest.TestCase):
    def _policy(self, **changes):
        groups = {
            "full": (FeatureTerm("R"),),
            "extreme": (FeatureTerm("extreme"),),
            "d_plus_r": (FeatureTerm("D"), FeatureTerm("R")),
            "d_only": (FeatureTerm("D"),),
            "d_l_interaction": (FeatureTerm("D"), FeatureTerm("D_x_L", "PRODUCT", ("D", "L"))),
            "no_interaction": (FeatureTerm("D"),),
            "liq_oi_r": (FeatureTerm("R"),),
            "liq_oi": (FeatureTerm("liq"), FeatureTerm("OI",)),
        }
        pairs = {
            "H-001": AblationPair("H-001", "full", "extreme"),
            "H-002": AblationPair("H-002", "d_plus_r", "d_only"),
            "H-003": AblationPair("H-003", "d_l_interaction", "no_interaction"),
            "H-004": AblationPair("H-004", "liq_oi_r", "liq_oi"),
        }
        values = dict(
            as_of=parse_utc("2026-03-01T00:00:00Z"), folds=2, embargo_seconds=0,
            feature_groups=groups, ablation_pairs=pairs, utility_feature_group="full",
            min_effective_episodes=28, min_effective_episodes_per_state=4,
            required_states=("THIN", "NORMAL", "DEEP"), min_utc_days=7,
            bootstrap_iterations=80, bootstrap_seed=7, base_round_trip_cost_bps=5,
            stress_round_trip_cost_bps=10, tp_gross_return_bps=30, sl_gross_return_bps=-12,
            relative_logloss_improvement_min=0.005,
        )
        values.update(changes)
        return G2EvaluatorPolicy(**values)

    def _rows(self, *, rows=56, constant_signal=False, direction="ALTERNATE"):
        outcomes = ("TP", "SL", "STRUCTURE_EXIT", "TIMEOUT")
        signals = (2.0, -2.0, 1.0, -1.0)
        rendered = []
        for index in range(rows):
            signal = 0.0 if constant_signal else signals[index % len(signals)]
            side = "BUY" if direction == "BUY" or index % 2 == 0 else "SELL"
            rendered.append({
                "availability_kind": "ACTUAL", "censored": False, "stage": "ENTER_PROBE",
                "episode_id": "episode-%03d" % index,
                "decision_at": "2026-01-%02dT00:00:00Z" % (index % 14 + 1),
                "label_end_at": "2026-01-%02dT00:01:00Z" % (index % 14 + 1),
                "side": side, "state_id": ("THIN", "NORMAL", "DEEP")[index % 3],
                "features": {"extreme": 0.0, "D": 1.0, "R": signal, "L": signal, "liq": 0.0, "OI": 0.0},
                "outcome": outcomes[index % 4], "gross_return_bps": 30.0,
            })
        return rendered

    def test_declared_ablation_gates_report_uplift_calibration_and_market_path_utility(self):
        report = evaluate_g2(self._rows(), policy=self._policy())
        self.assertEqual("G2_PASS", report["overall_status"])
        self.assertTrue(all(gate["status"] == "SUPPORT" for gate in report["gates"].values()))
        fold = report["ablations"]["H-001"]["folds"][0]
        self.assertIn("probability_deciles_one_vs_rest", fold["candidate"])
        self.assertIn("confusion", fold["candidate"])
        self.assertIn("recall_by_class", fold["candidate"])
        self.assertGreater(fold["candidate"]["accuracy"], fold["empirical_class_frequency"]["accuracy"])
        self.assertIn("candidate_temperature", fold)
        self.assertNotEqual(1.0, fold["candidate_temperature"])
        self.assertNotEqual(fold["candidate"]["log_loss"], fold["candidate_uncalibrated"]["log_loss"])
        self.assertLessEqual(fold["fit_latest_label_end_at"], fold["calibration_start_at"])
        self.assertLessEqual(fold["calibration_latest_label_end_at"], fold["test_start_at"])
        self.assertIn("counterfactual market-path utility", report["utility"]["meaning"])
        self.assertGreater(report["bootstrap_utc_day_block"]["lower_95_bps"], 0)

    def test_no_uplift_fails_after_sufficient_coverage_and_cannot_pass_g2(self):
        report = evaluate_g2(self._rows(constant_signal=True), policy=self._policy())
        self.assertEqual("FAIL", report["gates"]["H-001"]["status"])
        self.assertNotEqual("G2_PASS", report["overall_status"])

    def test_predictive_gate_fails_when_full_candidate_loses_to_empirical_frequency(self):
        rows = self._rows()
        inverse = {"TP": "SL", "SL": "TP", "STRUCTURE_EXIT": "TIMEOUT", "TIMEOUT": "STRUCTURE_EXIT"}
        for row in rows:
            if int(row["decision_at"][8:10]) >= 5:
                row["outcome"] = inverse[row["outcome"]]
        report = evaluate_g2(rows, policy=self._policy())
        self.assertEqual("FAIL", report["gates"]["PREDICTIVE"]["status"])
        self.assertEqual("G2_FAIL", report["overall_status"])

    def test_missing_declared_feature_waits_instead_of_zero_filling(self):
        rows = self._rows()
        del rows[0]["features"]["R"]
        report = evaluate_g2(rows, policy=self._policy())
        self.assertEqual("INCONCLUSIVE/WAIT_DATA", report["gates"]["H-001"]["status"])
        self.assertIn("missing required declared feature", report["ablations"]["H-001"]["reason"])
        self.assertNotEqual("G2_PASS", report["overall_status"])

    def test_censored_unknown_or_duplicate_input_is_rejected_fail_closed(self):
        rows = self._rows()
        rows[0]["censored"] = True
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())
        rows = self._rows()
        rows[1]["episode_id"] = rows[0]["episode_id"]
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())
        rows = self._rows()
        rows[0]["outcome"] = "UNKNOWN"
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())
        rows = self._rows()
        rows[0]["features"]["R"] = float("nan")
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())
        rows = self._rows()
        rows[0]["label_end_at"] = "2026-04-01T00:00:00Z"
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())
        rows = self._rows()
        rows[0]["state_id"] = "UNKNOWN"
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(rows, policy=self._policy())

    def test_utc_day_bootstrap_is_deterministic(self):
        first = evaluate_g2(self._rows(), policy=self._policy())
        second = evaluate_g2(copy.deepcopy(self._rows()), policy=self._policy())
        self.assertEqual(first["bootstrap_utc_day_block"], second["bootstrap_utc_day_block"])

    def test_direction_concentration_fails_stability_even_when_predictive_gates_support(self):
        report = evaluate_g2(self._rows(direction="BUY"), policy=self._policy())
        self.assertEqual("FAIL", report["gates"]["STABILITY"]["status"])
        self.assertFalse(report["concentration"]["dimensions"]["direction"]["passed"])
        self.assertLess(report["concentration"]["selected_episodes"], len(self._rows(direction="BUY")))
        self.assertNotEqual("G2_PASS", report["overall_status"])

    def test_zero_positive_ev_selection_waits_and_policy_rejects_invalid_proxies_or_identical_ablation(self):
        report = evaluate_g2(self._rows(), policy=self._policy(base_round_trip_cost_bps=100, stress_round_trip_cost_bps=120))
        self.assertEqual("INCONCLUSIVE/WAIT_DATA", report["gates"]["ECONOMIC"]["status"])
        self.assertEqual("INCONCLUSIVE/WAIT_DATA", report["gates"]["STABILITY"]["status"])
        self.assertEqual(0, report["utility"]["candidate"]["selected_episodes"])
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(self._rows(), policy=self._policy(sl_gross_return_bps=1))
        pairs = dict(self._policy().ablation_pairs)
        pairs["H-001"] = AblationPair("H-001", "full", "full")
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(self._rows(), policy=self._policy(ablation_pairs=pairs))
        groups = dict(self._policy().feature_groups)
        groups["extreme"] = (FeatureTerm("renamed_R", "IDENTITY", ("R",)),)
        with self.assertRaises(G2EvaluationError):
            evaluate_g2(self._rows(), policy=self._policy(feature_groups=groups))

    def test_separate_buy_sell_models_require_both_directions(self):
        policy = self._policy(separate_models=True, required_sides=("BUY", "SELL"), min_effective_episodes_per_side=20, min_effective_episodes_per_state_per_side=3)
        report = evaluate_g2(self._rows(), policy=policy)
        self.assertEqual({"BUY", "SELL"}, set(report["directional_models"]))
        self.assertIn("gates", report)
        missing = evaluate_g2(self._rows(direction="BUY"), policy=policy)
        self.assertEqual("INCONCLUSIVE/WAIT_DATA", missing["directional_models"]["SELL"]["overall_status"])
