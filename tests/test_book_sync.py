import unittest

from trade_system.book_sync import BinanceBookSynchronizer
from trade_system.order_book import OrderBook
from trade_system.types import BookHealth


class BookSynchronizerTests(unittest.TestCase):
    def test_buffered_deltas_connect_after_snapshot(self):
        book = OrderBook()
        sync = BinanceBookSynchronizer(book)
        sync.buffer_delta({"kind": "delta", "U": 99, "u": 100, "pu": 98, "bids": [], "asks": []})
        sync.buffer_delta({"kind": "delta", "U": 101, "u": 101, "pu": 100, "bids": [["99", "2"]], "asks": []})
        sync.buffer_delta({"kind": "delta", "U": 102, "u": 102, "pu": 101, "bids": [], "asks": [["101", "2"]]})
        sync.apply_snapshot({"kind": "snapshot", "last_update_id": 100, "bids": [["99", "1"]], "asks": [["101", "1"]]})
        self.assertEqual(BookHealth.VALID, book.health)
        self.assertEqual(102, book.last_update_id)

    def test_snapshot_without_buffer_is_valid_until_live_delta(self):
        book = OrderBook()
        sync = BinanceBookSynchronizer(book)
        sync.apply_snapshot({"kind": "snapshot", "last_update_id": 100, "bids": [["99", "1"]], "asks": [["101", "1"]]})
        self.assertEqual(BookHealth.VALID, book.health)
        sync.apply_live_delta({"kind": "delta", "U": 101, "u": 101, "pu": 100, "bids": [], "asks": []})
        self.assertEqual(101, book.last_update_id)
