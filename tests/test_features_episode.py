import unittest
from datetime import timedelta
from decimal import Decimal

from trade_system.episode import EpisodeMachine
from trade_system.features import FeatureEngine
from trade_system.order_book import OrderBook
from trade_system.types import AvailabilityKind, EpisodeState, Side, TradePrint, utc_now


class FeaturesEpisodeTests(unittest.TestCase):
    def test_censored_liquidation_is_flagged_without_becoming_zero(self):
        now = utc_now()
        book = OrderBook()
        book.reset_snapshot(last_update_id=1, bids=[["99", "3"]], asks=[["101", "3"]])
        engine = FeatureEngine(window=timedelta(seconds=30))
        engine.add_trade(TradePrint(now, Decimal("100"), Decimal("2"), Side.SELL))
        engine.add_liquidation(now, Side.SELL, Decimal("100"), Decimal("1"), censored=True)
        snapshot = engine.snapshot(available_at=now, book=book, availability_kind=AvailabilityKind.ACTUAL)
        self.assertLess(snapshot.values["F_forced_pressure"], 0)
        self.assertIn("liquidation_censored", snapshot.quality_flags)
        self.assertNotIn("liquidation_unobserved", snapshot.quality_flags)

    def test_book_invalid_forces_episode_unknown(self):
        now = utc_now()
        book = OrderBook()
        engine = FeatureEngine()
        snapshot = engine.snapshot(available_at=now, book=book, availability_kind=AvailabilityKind.ACTUAL)
        machine = EpisodeMachine()
        machine.observe_extreme(now=now, price=Decimal("100"), reversal_side=Side.BUY)
        episode = machine.advance(snapshot)
        self.assertEqual(EpisodeState.UNKNOWN, episode.state)

    def test_missing_oi_and_crowding_are_quality_flags_not_silent_zeros(self):
        now = utc_now()
        book = OrderBook()
        book.reset_snapshot(last_update_id=1, bids=[["99", "3"]], asks=[["101", "3"]])
        engine = FeatureEngine()
        missing = engine.snapshot(available_at=now, book=book, availability_kind=AvailabilityKind.ACTUAL)
        self.assertIn("open_interest_unavailable", missing.quality_flags)
        self.assertIn("crowding_unavailable", missing.quality_flags)
        engine.update_open_interest(Decimal("1000"))
        engine.update_crowding(funding_rate=Decimal("0.001"), premium=Decimal("0"))
        observed = engine.snapshot(available_at=now, book=book, availability_kind=AvailabilityKind.ACTUAL)
        self.assertNotIn("open_interest_unavailable", observed.quality_flags)
        self.assertNotIn("crowding_unavailable", observed.quality_flags)
