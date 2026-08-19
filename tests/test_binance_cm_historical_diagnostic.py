import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trade_system.binance_cm_historical_diagnostic import BarrierTrade, DiagnosticTiming, FeatureWindow, HistoricalDiagnosticError, HistoricalDiagnosticPlan, build_extreme_diagnostic_row, execute_frozen_before_download, label_barrier_path, select_positive_ev


UTC = timezone.utc


class HistoricalDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.plan = HistoricalDiagnosticPlan.load(Path(__file__).resolve().parents[1] / "config/binance_cm_historical_diagnostic.v2.frozen_before_download.json")
        self.start = datetime(2025, 2, 1, 0, 0, tzinfo=UTC)

    def _timing(self):
        p = self.start + timedelta(minutes=5)
        return DiagnosticTiming(p, p, p + timedelta(seconds=60), p + timedelta(seconds=61), p + timedelta(seconds=61, milliseconds=250), p + timedelta(minutes=6, seconds=61, milliseconds=250), p + timedelta(minutes=2), p + timedelta(minutes=6, seconds=61, milliseconds=250))

    def _window(self, start, end):
        return FeatureWindow(start, end, end, 0, 30)

    def test_frozen_before_download_refuses_execution(self):
        with self.assertRaises(HistoricalDiagnosticError):
            execute_frozen_before_download(self.plan)

    def test_extreme_is_watch_then_abstains_without_response_snapshots(self):
        p = self.start + timedelta(minutes=5); response = self._window(p, p + timedelta(seconds=60))
        row = build_extreme_diagnostic_row(plan=self.plan, d_pressure_proxy=2.0, r_response_proxy=0.1, l_oi_proxy=0.02, state_id="NORMAL_BOOK", pressure_window=self._window(self.start, p), response_window=response, oi_window=self._window(self.start, p), timing=self._timing(), response_snapshot_count=1, side="SELL")
        self.assertEqual("WATCH", row["stage"])
        self.assertEqual("ABSTAIN", row["status"])
        self.assertEqual("INSUFFICIENT_POST_PRESSURE_BOOK_SNAPSHOTS", row["reason"])

    def test_timing_gap_and_same_timestamp_barrier_are_conservative(self):
        p = self.start + timedelta(minutes=5)
        stale = FeatureWindow(self.start, p, p, self.plan.max_book_age_seconds + 1, 30)
        with self.assertRaises(HistoricalDiagnosticError):
            build_extreme_diagnostic_row(plan=self.plan, d_pressure_proxy=2.0, r_response_proxy=0.1, l_oi_proxy=0.02, state_id="NORMAL_BOOK", pressure_window=stale, response_window=self._window(p, p + timedelta(seconds=60)), oi_window=self._window(self.start, p), timing=self._timing(), response_snapshot_count=2, side="SELL")
        at = self.start + timedelta(seconds=1)
        label = label_barrier_path(side="BUY", entry_price=100, tp_bps=20, sl_bps=12, horizon_end=at + timedelta(seconds=1), trades=[BarrierTrade(at, 2, 100.3), BarrierTrade(at, 3, 99.7)])
        self.assertEqual("SL", label["outcome"])
        self.assertTrue(label["same_timestamp_conservative_sl"])

    def test_selected_only_when_base_ev_is_positive(self):
        self.assertTrue(select_positive_ev(probabilities={"TP": .8, "SL": .1, "TIMEOUT": .1}, base_cost_bps=10, tp_bps=20, sl_bps=12, timeout_payoff_bps=0)["selected"])
        self.assertFalse(select_positive_ev(probabilities={"TP": .2, "SL": .6, "TIMEOUT": .2}, base_cost_bps=10, tp_bps=20, sl_bps=12, timeout_payoff_bps=0)["selected"])
