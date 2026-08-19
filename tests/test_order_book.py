import unittest
from decimal import Decimal

from trade_system.order_book import BookGapError, OrderBook
from trade_system.types import BookHealth, Side


class OrderBookTests(unittest.TestCase):
    def setUp(self):
        self.book = OrderBook()
        self.book.reset_snapshot(
            last_update_id=10,
            bids=[["99", "1"], ["98", "2"]],
            asks=[["101", "1"], ["102", "2"]],
        )

    def test_contiguous_delta_and_ioc_partial_fill(self):
        self.book.apply_delta(first_update_id=11, final_update_id=11, previous_final_update_id=10, bids=[["99", "2"]], asks=[])
        self.assertEqual(Decimal("2"), self.book.bids[Decimal("99")])
        fill = self.book.estimate_ioc(Side.BUY, Decimal("2"), Decimal("101"))
        self.assertEqual(Decimal("1"), fill.filled_quantity)
        self.assertEqual(Decimal("1"), fill.remaining_quantity)
        self.assertEqual(Decimal("101"), fill.average_price)

    def test_first_delta_may_overlap_snapshot_but_later_delta_cannot(self):
        self.book.apply_delta(first_update_id=9, final_update_id=11, previous_final_update_id=8, bids=[["99", "2"]], asks=[])
        self.book.apply_delta(first_update_id=12, final_update_id=12, previous_final_update_id=11, bids=[], asks=[])
        self.assertEqual(12, self.book.last_update_id)

    def test_followup_aggregated_delta_uses_pu_not_numeric_u_adjacency(self):
        self.book.apply_delta(first_update_id=11, final_update_id=11, previous_final_update_id=10, bids=[], asks=[])
        self.book.apply_delta(first_update_id=20, final_update_id=25, previous_final_update_id=11, bids=[], asks=[])
        self.assertEqual(25, self.book.last_update_id)

    def test_gap_invalidates_book_and_blocks_execution(self):
        with self.assertRaises(BookGapError):
            self.book.apply_delta(first_update_id=13, final_update_id=13, previous_final_update_id=10, bids=[], asks=[])
        self.assertEqual(BookHealth.INVALID, self.book.health)
        with self.assertRaises(BookGapError):
            self.book.estimate_ioc(Side.BUY, Decimal("1"), Decimal("101"))

    def test_default_depth_tracks_top_levels_across_delta_updates(self):
        self.book.reset_snapshot(
            last_update_id=10,
            bids=[[str(price), "1"] for price in range(99, 92, -1)],
            asks=[[str(price), "1"] for price in range(101, 108)],
        )
        self.assertEqual(Decimal("485"), self.book.depth_notional(Side.SELL))
        self.assertEqual(Decimal("515"), self.book.depth_notional(Side.BUY))

        self.book.apply_delta(
            first_update_id=11,
            final_update_id=11,
            previous_final_update_id=10,
            bids=[["99", "2"], ["98", "0"]],
            asks=[["100", "3"], ["103", "0"]],
        )
        self.assertEqual(Decimal("580"), self.book.depth_notional(Side.SELL))
        self.assertEqual(Decimal("712"), self.book.depth_notional(Side.BUY))
        self.assertEqual(Decimal("391"), self.book.depth_notional(Side.SELL, levels=3))
        self.assertEqual(Decimal("503"), self.book.depth_notional(Side.BUY, levels=3))
