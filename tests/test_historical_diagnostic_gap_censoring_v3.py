import unittest
from datetime import date, datetime, timedelta, timezone

from trade_system.historical_diagnostic_gap_censoring_v3 import (
    FiveMinuteSlotLedger,
    FutureGapCensoringError,
    SlotEvidence,
    build_canonical_gap_index,
    classify_five_minute_slot,
    gap_intersects_window,
    intersecting_gap_ids,
    validate_official_book_depth_rows,
    validate_official_metrics_rows,
)


UTC = timezone.utc
DAY = date(2025, 7, 1)
ARCHIVE_SHA = "a" * 64
TIMING = {
    "pressure_window_seconds": 300,
    "response_window_seconds": 60,
    "decision_delay_after_response_seconds": 1,
    "entry_latency_ms": 250,
    "max_entry_wait_seconds": 60,
    "path_horizon_seconds": 300,
    "max_path_trade_age_seconds": 60,
    "max_path_trade_gap_seconds": 60,
    "max_book_age_seconds": 30,
    "max_book_gap_seconds": 60,
    "max_oi_age_seconds": 300,
    "max_oi_gap_seconds": 300,
}


def at(hour, minute=0, second=0):
    return datetime(2025, 7, 1, hour, minute, second, tzinfo=UTC)


def index(kind, times, *, archive_sha=ARCHIVE_SHA, policy=TIMING):
    return build_canonical_gap_index(
        archive_sha256=archive_sha,
        kind=kind,
        day=DAY,
        affected_file="BTCUSD_PERP-%s-2025-07-01.csv" % kind,
        observation_times=times,
        timing_policy=policy,
    )


class FutureGapCensoringV3Tests(unittest.TestCase):
    def test_canonical_index_binds_archive_and_records_61s_23m_multigap_without_exception(self):
        result = index("bookDepth", [at(0), at(0, 1, 1), at(0, 24, 1), at(0, 25, 2)])
        internal = [gap for gap in result["gaps"] if gap["interval_type"] == "INTERNAL"]
        self.assertEqual(ARCHIVE_SHA, result["archive_sha256"])
        self.assertEqual(4, result["observation_count"])
        self.assertEqual([61_000, 1_380_000, 61_000], [gap["delta_ms"] for gap in internal])
        self.assertTrue(all(gap["threshold_field"] == "max_book_gap_seconds" for gap in internal))
        self.assertTrue(all(gap["semantics"] == "OBSERVED_CADENCE_ABSENCE_OPEN_INTERVAL_NO_FILL" for gap in internal))
        self.assertEqual(len({gap["gap_id"] for gap in result["gaps"]}), result["gap_count"])
        self.assertEqual(result["canonical_sha256"], build_canonical_gap_index(
            archive_sha256=ARCHIVE_SHA, kind="bookDepth", day=DAY,
            affected_file="BTCUSD_PERP-bookDepth-2025-07-01.csv",
            observation_times=[at(0), at(0, 1, 1), at(0, 24, 1), at(0, 25, 2)], timing_policy=TIMING,
        )["canonical_sha256"])

    def test_metrics_uses_oi_internal_gap_and_age_edge_thresholds(self):
        result = index("metrics", [at(0, 5, 1), at(0, 28, 1)])
        start_gap, internal = result["gaps"][:2]
        self.assertEqual(("START_AGE", "max_oi_age_seconds", 301_000), (start_gap["interval_type"], start_gap["threshold_field"], start_gap["delta_ms"]))
        self.assertEqual(("INTERNAL", "max_oi_gap_seconds", 1_380_000), (internal["interval_type"], internal["threshold_field"], internal["delta_ms"]))

    def test_official_book_shape_allows_extra_levels_and_zero_but_requires_exact_pm_one(self):
        stamp = at(0)
        rows = [
            {"timestamp": stamp, "percentage": value, "depth": "1"}
            for value in (-5, -1, 0, 1, 5)
        ]
        self.assertEqual([stamp], validate_official_book_depth_rows(rows, day=DAY))
        with self.assertRaises(FutureGapCensoringError):
            validate_official_book_depth_rows(rows + [{"timestamp": stamp, "percentage": -1, "depth": "1"}], day=DAY)
        with self.assertRaises(FutureGapCensoringError):
            validate_official_book_depth_rows([{"timestamp": stamp, "percentage": -1, "depth": "0"}, {"timestamp": stamp, "percentage": 1, "depth": "1"}], day=DAY)

    def test_metrics_symbol_and_open_interest_field_mixing_are_hard_rejected(self):
        row = {"create_time": at(0), "symbol": "BTCUSD_PERP", "sum_open_interest": "1"}
        self.assertEqual([at(0)], validate_official_metrics_rows([row], day=DAY))
        with self.assertRaises(FutureGapCensoringError):
            validate_official_metrics_rows([{**row, "symbol": "WRONG"}], day=DAY)
        with self.assertRaises(FutureGapCensoringError):
            validate_official_metrics_rows([{"create_time": at(0), "symbol": "BTCUSD_PERP", "sum_open_interest_value": "1"}], day=DAY)

    def test_open_gap_intersection_has_safe_boundary_behavior(self):
        book_index = index("bookDepth", [at(0), at(0, 5), at(0, 10), at(23, 59, 59)])
        gap = next(gap for gap in book_index["gaps"] if gap["interval_type"] == "INTERNAL" and gap["left_at"] == at(0, 5).isoformat())
        self.assertFalse(gap_intersects_window(gap, start=at(0, 4), end=at(0, 5)))
        self.assertFalse(gap_intersects_window(gap, start=at(0, 10), end=at(0, 11)))
        self.assertTrue(gap_intersects_window(gap, start=at(0, 6), end=at(0, 7)))
        self.assertEqual([gap["gap_id"]], intersecting_gap_ids(book_index, kind="bookDepth", day=DAY, start=at(0, 6), end=at(0, 7)))

    def _valid_indexes(self):
        return (
            index("bookDepth", [at(0), at(0, 4, 30), at(0, 5), at(0, 5, 30), at(0, 6), at(0, 6, 30), at(0, 7), at(0, 7, 30), at(0, 8), at(0, 8, 30), at(0, 9), at(0, 9, 30), at(0, 10), at(0, 10, 30), at(0, 11), at(0, 34), at(23, 59, 59)]),
            index("metrics", [at(0), at(0, 5), at(0, 10), at(0, 15), at(23, 59, 59)]),
        )

    def _valid_evidence(self, **changes):
        evidence = SlotEvidence(
            slot_at=at(0, 10), pressure_book_at=at(0, 10), response_book_times=[at(0, 10, 30), at(0, 11)],
            oi_start_at=at(0, 5), oi_end_at=at(0, 10), eligible_trade_at=at(0, 11, 30),
            path_trade_times=[at(0, 11, 30), at(0, 12, 30), at(0, 13, 30), at(0, 14, 30), at(0, 15, 30), at(0, 16)],
            signal_present=True, row_sha256="b" * 64,
        )
        return SlotEvidence(**{**evidence.__dict__, **changes})

    def test_23m_gap_with_fresh_endpoint_is_censored_not_leaked(self):
        book = index("bookDepth", [at(0), at(6, 44), at(6, 49, 30), at(6, 50), at(6, 50, 30), at(6, 51), at(23, 59, 59)])
        metrics = index("metrics", [at(0), at(6, 45), at(6, 50), at(23, 59, 59)])
        outcome = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(slot_at=at(6, 50), pressure_book_at=at(6, 50), response_book_times=[at(6, 50, 30), at(6, 51)], oi_start_at=at(6, 45), oi_end_at=at(6, 50)), timing_policy=TIMING, book_index=book, metrics_index=metrics)
        self.assertEqual("CENSORED_DATA_QUALITY", outcome["state"])
        self.assertIn("book_pressure_intersects_observed_cadence_gap", outcome["reason"])
        self.assertTrue(outcome["gap_ids"])

    def test_response_bridge_internal_tail_and_oi_age_gap_are_censored(self):
        policy = dict(TIMING, response_window_seconds=180, max_oi_age_seconds=30)
        book = index("bookDepth", [at(0), at(0, 5), at(0, 10), at(0, 10, 45), at(0, 12), at(0, 13), at(23, 59, 59)], policy=policy)
        metrics = index("metrics", [at(0), at(0, 4), at(0, 10), at(23, 59, 59)], policy=policy)
        outcome = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(response_book_times=[at(0, 10, 45), at(0, 12)], oi_start_at=at(0, 4), oi_end_at=at(0, 10)), timing_policy=policy, book_index=book, metrics_index=metrics)
        self.assertEqual("CENSORED_DATA_QUALITY", outcome["state"])
        self.assertIn("response_book_bridge_exceeds_limit", outcome["reason"])
        self.assertIn("response_book_internal_gap_exceeds_limit", outcome["reason"])
        self.assertIn("response_book_tail_exceeds_limit", outcome["reason"])
        self.assertIn("oi_start_age_exceeds_limit", outcome["reason"])
        self.assertIn("oi_gap_exceeds_limit", outcome["reason"])

    def test_trade_entry_path_tail_and_signal_have_distinct_terminal_states(self):
        book, metrics = self._valid_indexes()
        path_failure = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(eligible_trade_at=at(0, 12, 30), path_trade_times=[at(0, 12, 30), at(0, 14), at(0, 16)]), timing_policy=TIMING, book_index=book, metrics_index=metrics)
        self.assertEqual("CENSORED_LABEL_PATH", path_failure["state"])
        self.assertIn("entry_trade_wait_exceeds_limit", path_failure["reason"])
        self.assertIn("label_path_internal_gap_exceeds_limit", path_failure["reason"])
        abstain = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(signal_present=False), timing_policy=TIMING, book_index=book, metrics_index=metrics)
        self.assertEqual("ABSTAIN_SIGNAL", abstain["state"])
        eligible = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(), timing_policy=TIMING, book_index=book, metrics_index=metrics)
        self.assertEqual("ELIGIBLE_ROW", eligible["state"])
        self.assertEqual("b" * 64, eligible["row_sha256"])

    def test_slot_ledger_is_unique_and_cross_day_and_aggtrade_acquisition_gaps_are_refused(self):
        ledger = FiveMinuteSlotLedger(day=DAY)
        outcome = {"slot_at": at(0, 5).isoformat(), "state": "CENSORED_DATA_QUALITY", "reason": ["synthetic"], "windows": [], "gap_ids": []}
        ledger.record(outcome)
        with self.assertRaises(FutureGapCensoringError):
            ledger.record(outcome)
        with self.assertRaises(FutureGapCensoringError):
            ledger.require_complete(first_slot=at(0, 5), last_slot=at(0, 10))
        ledger.record({"slot_at": at(0, 10).isoformat(), "state": "ABSTAIN_SIGNAL"})
        self.assertEqual(2, len(ledger.require_complete(first_slot=at(0, 5), last_slot=at(0, 10))))
        with self.assertRaises(FutureGapCensoringError):
            build_canonical_gap_index(archive_sha256=ARCHIVE_SHA, kind="aggTrades", day=DAY, affected_file="synthetic.csv", observation_times=[at(0)], timing_policy=TIMING)
        with self.assertRaises(FutureGapCensoringError):
            index("metrics", [datetime(2025, 7, 2, tzinfo=UTC)])
        book = index("bookDepth", [at(0), at(23, 49, 30), at(23, 50), at(23, 50, 30), at(23, 51), at(23, 51, 30), at(23, 52), at(23, 52, 30), at(23, 53), at(23, 53, 30), at(23, 54), at(23, 54, 30), at(23, 55), at(23, 55, 30), at(23, 56), at(23, 59, 59)])
        metrics = index("metrics", [at(0), at(23, 50), at(23, 55), at(23, 59, 59)])
        cross_day = classify_five_minute_slot(day=DAY, evidence=self._valid_evidence(slot_at=at(23, 55), pressure_book_at=at(23, 55), response_book_times=[at(23, 55, 30), at(23, 56)], oi_start_at=at(23, 50), oi_end_at=at(23, 55)), timing_policy=TIMING, book_index=book, metrics_index=metrics)
        self.assertEqual("CENSORED_LABEL_PATH", cross_day["state"])
        self.assertIn("label_path_crosses_utc_day", cross_day["reason"])


if __name__ == "__main__":
    unittest.main()
