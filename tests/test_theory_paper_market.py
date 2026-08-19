from __future__ import annotations

import unittest
from datetime import datetime, timezone

from trade_system.theory_paper.market import (
    _closed_bars,
    equity_reference_context,
    fetch_symbol_snapshot,
)


class TheoryPaperMarketTests(unittest.TestCase):
    def test_open_bar_is_excluded(self) -> None:
        rows = [
            [0, "1", "2", "0.5", "1.5", "10", 999],
            [1000, "1.5", "3", "1", "2", "20", 2001],
        ]
        self.assertEqual(len(_closed_bars(rows, 2000)), 1)

    def test_equity_perpetual_is_not_described_as_cash_equity(self) -> None:
        context = equity_reference_context(
            "SNDKUSDT",
            datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            context["instrument_kind"],
            "TRADIFI_EQUITY_PERPETUAL_DERIVATIVE",
        )
        self.assertIn("SCHEDULE_ESTIMATE", context["underlying_session"])

    def test_missing_oi_history_remains_unknown_instead_of_crashing_or_zero(self) -> None:
        observed = datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc)
        closed = [
            [index * 60_000, "100", "102", "99", str(100 + index / 10), "10", index * 60_000 + 59_999]
            for index in range(60)
        ]

        def getter(path: str, params: dict[str, object]) -> object:
            if path.endswith("ticker/24hr"):
                return {
                    "lastPrice": "106",
                    "priceChangePercent": "1",
                    "highPrice": "107",
                    "lowPrice": "99",
                    "quoteVolume": "100000",
                    "count": 100,
                }
            if path.endswith("premiumIndex"):
                return {"markPrice": "106", "indexPrice": "105.9"}
            if path.endswith("openInterest"):
                return {"openInterest": "1000"}
            if path.endswith("openInterestHist"):
                raise OSError("unavailable")
            if path.endswith("depth"):
                return {"bids": [["105.9", "20"]], "asks": [["106.1", "20"]]}
            if path.endswith("aggTrades"):
                return [{"p": "106", "q": "1", "m": False}]
            if path.endswith("klines"):
                return closed
            return []

        snapshot = fetch_symbol_snapshot("SNDKUSDT", getter, observed_at=observed)
        self.assertIsNone(
            snapshot["measures"]["leverage_L"]["open_interest_value_1h_change_pct"]
        )
        self.assertGreater(snapshot["data_quality"]["error_count"], 0)
        self.assertFalse(snapshot["data_quality"]["strict_R_available"])


if __name__ == "__main__":
    unittest.main()
