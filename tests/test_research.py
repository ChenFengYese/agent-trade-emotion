import unittest
from datetime import timedelta

from trade_system.decision import MarketOutcome
from trade_system.research import LabeledObservation, RegularizedMultinomialLogistic, assess_state_coverage, purged_walk_forward, run_final_holdout_baseline, run_walk_forward_baseline
from trade_system.types import utc_now


class ResearchTests(unittest.TestCase):
    def _rows(self):
        base = utc_now()
        rows = []
        for index in range(18):
            at = base + timedelta(minutes=index * 5)
            positive = 1.0 if index % 2 else -1.0
            outcome = MarketOutcome.TP if positive > 0 else MarketOutcome.SL
            rows.append(LabeledObservation(
                episode_id="episode-%d" % index,
                decision_at=at,
                label_end_at=at + timedelta(minutes=1),
                features={"pressure": positive},
                outcome=outcome,
                state_id="CALM" if index % 3 else "STRESSED",
            ))
        return rows

    def test_purged_walk_forward_never_uses_overlapping_future_labels(self):
        folds = purged_walk_forward(self._rows(), folds=3, embargo=timedelta(minutes=1))
        for fold in folds:
            first_test = fold.test[0].decision_at
            self.assertTrue(all(item.label_end_at <= first_test - timedelta(minutes=1) for item in fold.train))

    def test_logistic_baseline_learns_directional_toy_feature(self):
        model = RegularizedMultinomialLogistic(["pressure"], epochs=400).fit(self._rows())
        positive = model.predict({"pressure": 1.0})
        negative = model.predict({"pressure": -1.0})
        self.assertGreater(positive.tp, positive.sl)
        self.assertGreater(negative.sl, negative.tp)

    def test_walk_forward_report_contains_metrics(self):
        report = run_walk_forward_baseline(self._rows(), feature_names=["pressure"], folds=3, embargo=timedelta(minutes=1))
        self.assertGreater(len(report.folds), 0)
        self.assertGreaterEqual(report.mean_brier, 0.0)

    def test_final_holdout_baseline_fits_only_pre_holdout_rows(self):
        rows = self._rows()
        report = run_final_holdout_baseline(rows[:12], rows[12:], feature_names=["pressure"])
        self.assertEqual(12, report.training_observations)
        self.assertEqual(6, report.holdout_observations)
        self.assertGreaterEqual(report.metrics.multiclass_brier, 0.0)

    def test_state_coverage_rejects_unassigned_or_underrepresented_rows(self):
        rows = self._rows()
        report = assess_state_coverage(
            rows,
            required_state_ids=("CALM", "STRESSED", "DISLOCATED"),
            min_effective_episodes_per_state=3,
        )
        self.assertFalse(report.passed)
        self.assertEqual(("DISLOCATED",), report.missing_state_ids)
        self.assertEqual((), report.unexpected_state_ids)
        unassigned = list(rows)
        unassigned[0] = LabeledObservation(
            episode_id="unassigned", decision_at=rows[0].decision_at, label_end_at=rows[0].label_end_at,
            features=rows[0].features, outcome=rows[0].outcome,
        )
        rejected = assess_state_coverage(
            unassigned,
            required_state_ids=("CALM", "STRESSED"),
            min_effective_episodes_per_state=1,
        )
        self.assertFalse(rejected.passed)
        self.assertEqual(("UNASSIGNED",), rejected.unexpected_state_ids)
